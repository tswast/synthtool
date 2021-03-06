# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import pathlib
import pytest
import re
import shutil
import subprocess

from synthtool import metadata
from synthtool.tmp import tmpdir


def test_add_git_source():
    metadata.reset()

    metadata.add_git_source(sha="sha", name="name", remote="remote")

    current = metadata.get()

    assert current.sources[0].git.sha == "sha"
    assert current.sources[0].git.name == "name"
    assert current.sources[0].git.remote == "remote"


def test_add_generator_source():
    metadata.reset()

    metadata.add_generator_source(name="name", version="1.2.3")

    current = metadata.get()

    assert current.sources[0].generator.name == "name"
    assert current.sources[0].generator.version == "1.2.3"


def test_add_template_source():
    metadata.reset()

    metadata.add_template_source(name="name", version="1.2.3")

    current = metadata.get()

    assert current.sources[0].template.name == "name"
    assert current.sources[0].template.version == "1.2.3"


def add_sample_client_destination():
    metadata.add_client_destination(
        source="source",
        api_name="api",
        api_version="v1",
        language="py",
        generator="gen",
        config="config",
    )


def test_add_client_destination():
    metadata.reset()

    add_sample_client_destination()

    current = metadata.get()

    assert current.destinations[0].client.source == "source"
    assert current.destinations[0].client.api_name == "api"
    assert current.destinations[0].client.api_version == "v1"
    assert current.destinations[0].client.language == "py"
    assert current.destinations[0].client.generator == "gen"
    assert current.destinations[0].client.config == "config"


def test_write(tmpdir):
    metadata.reset()

    metadata.add_git_source(sha="sha", name="name", remote="remote")

    output_file = tmpdir / "synth.metadata"

    metadata.write(str(output_file))

    raw = output_file.read()

    # Ensure the file was written, that *some* metadata is in it, and that it
    # is valid JSON.
    assert raw
    assert "sha" in raw
    data = json.loads(raw)
    assert data
    assert data["updateTime"] is not None


class SourceTree:
    """Utility for quickly creating files in a sample source tree."""

    def __init__(self, tmpdir):
        metadata.reset()
        self.tmpdir = tmpdir
        self.git = shutil.which("git")
        subprocess.run([self.git, "init"])

    def write(self, path: str, content: str = None):
        parent = pathlib.Path(path).parent
        os.makedirs(parent, exist_ok=True)
        with open(path, "wt") as file:
            file.write(content or path)

    def git_add(self, *files):
        subprocess.run([self.git, "add"] + list(files))

    def git_commit(self, message):
        subprocess.run([self.git, "commit", "-m", message])


@pytest.fixture()
def source_tree():
    tmp_dir = tmpdir()
    cwd = os.getcwd()
    os.chdir(tmp_dir)
    yield SourceTree(tmp_dir)
    os.chdir(cwd)


def test_read_metadata(tmpdir):
    metadata.reset()
    add_sample_client_destination()
    metadata.write(tmpdir / "synth.metadata")
    read_metadata = metadata._read_or_empty(tmpdir / "synth.metadata")
    assert metadata.get() == read_metadata


def test_read_nonexistent_metadata(tmpdir):
    # The file doesn't exist.
    read_metadata = metadata._read_or_empty(tmpdir / "synth.metadata")
    metadata.reset()
    assert metadata.get() == read_metadata


@pytest.fixture(scope="function")
def preserve_track_obsolete_file_flag():
    should_track_obselete_files = metadata.should_track_obsolete_files()
    yield should_track_obselete_files
    metadata.set_track_obsolete_files(should_track_obselete_files)


def test_track_obsolete_files_defaults_to_false(preserve_track_obsolete_file_flag):
    assert not metadata.should_track_obsolete_files()


def test_append_git_log_to_metadata(source_tree):
    with metadata.MetadataTrackerAndWriter(source_tree.tmpdir / "synth.metadata"):
        # Create one commit that will be recorded in the metadata.
        source_tree.write("a")
        source_tree.git_add("a")
        source_tree.git_commit("a")

        hash = subprocess.run(
            [source_tree.git, "log", "-1", "--pretty=format:%H"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
        ).stdout.strip()
        metadata.add_git_source(name="tmp", local_path=os.getcwd(), sha=hash)

    metadata.reset()
    with metadata.MetadataTrackerAndWriter(source_tree.tmpdir / "synth.metadata"):
        # Create two more commits that should appear in metadata git log.
        source_tree.write("code/b")
        source_tree.git_add("code/b")
        source_tree.git_commit("code/b")

        source_tree.write("code/c")
        source_tree.git_add("code/c")
        source_tree.git_commit("code/c")

        hash = subprocess.run(
            [source_tree.git, "log", "-1", "--pretty=format:%H"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
        ).stdout.strip()
        metadata.add_git_source(name="tmp", local_path=os.getcwd(), sha=hash)

    # Read the metadata that we just wrote.
    mdata = metadata._read_or_empty(source_tree.tmpdir / "synth.metadata")
    # Match 2 log lines.
    assert re.match(
        r"[0-9A-Fa-f]+\ncode/c\n+[0-9A-Fa-f]+\ncode/b\n+",
        mdata.sources[0].git.log,
        re.MULTILINE,
    )
    # Make sure the local path field is not recorded.
    assert not mdata.sources[0].git.local_path is None


def test_reading_metadata_with_deprecated_fields_doesnt_crash(tmpdir):
    metadata_path = tmpdir / "synth.metadata"
    metadata_path.write_text(
        """
{
  "updateTime": "2020-01-28T12:42:19.618670Z",
  "newFiles": [
    {
      "path": ".eslintignore"
    }
  ]
}
""",
        "utf-8",
    )
    metadata._read_or_empty()
