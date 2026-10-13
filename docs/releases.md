# Versions and releases

## Version contract

Application releases use `MAJOR.MINOR.PATCH` and annotated Git tags such as `v0.1.0`. The matching GitHub Release includes a changelog, source archives, SHA-256 checksums, setup links, and known limitations. See [Semantic Versioning](https://semver.org/) for the version format.

- Patch releases fix behavior without an intentional compatibility break.
- Minor releases add features. While the application is `0.x`, minor releases can also change interfaces or configuration; review migration notes before upgrading.
- A future `1.0.0` release will establish a production compatibility contract after its release gates are met. The current `0.1.0` release does not claim the full production V1 roadmap is certified.

Published versions and tags are immutable. Fix a published release by creating a new version, not by moving its tag or replacing its source assets. Pre-release channels are not used for the initial release.

Application versions are separate from REST route prefixes such as `/api/v1`, immutable workflow version numbers, and database migration revisions. Changing an application version does not renumber workflows or migrations.

## Install a specific release

```sh
git clone --branch v0.1.0 --depth 1 https://github.com/FantoX/OxyBridge.git
cd OxyBridge
```

Alternatively, download a source archive from [Releases](https://github.com/FantoX/OxyBridge/releases), verify it against the attached `SHA256SUMS`, and extract it. Source archives include configuration examples, migrations, frontend/backend source, license files, and documentation. They exclude instance credentials, local state, installed dependencies, and database contents.

```powershell
Get-FileHash .\OxyBridge-v0.1.0-source.zip -Algorithm SHA256
```

Then follow [README setup](../README.md#get-started). These are source distributions; dependencies and the production UI must be built. No container registry image or package registry publication is implied. Build an image from the tagged checkout when needed:

```sh
docker build -t oxybridge:0.1.0 .
```

## Prepare the next release

1. Update `pyproject.toml`, root/frontend `package.json` and their lockfile root records, the OxyBridge entry in `uv.lock`, and the three application version values in `oxybridge/api.py`. Update the README version badge.
2. Move completed changes from `Unreleased` into a dated changelog section. Include schema/configuration changes, upgrade steps, validation evidence, and remaining limitations. Never edit previously published migrations in place.
3. Run `python scripts/check_release.py --tag vX.Y.Z`, the relevant local checks, and the full CI pipeline. Review the source and reachable Git history for private data before public publication. Refresh dependency notices if dependencies changed.
4. Commit and push the release preparation. Create an annotated tag on the verified commit: `git tag -a vX.Y.Z COMMIT_SHA -m "OxyBridge vX.Y.Z"`, then push that tag.
5. Generate source archives with a versioned top-level directory using `git archive`, calculate SHA-256 checksums, and create a GitHub Release for the tag. Publish only committed, reviewed source. Inspect archive contents before uploading.
6. Verify that release assets download, checksums match, the tag points to the intended commit, and the README/release links render. Promote the release in your hosting environment using the [operations guide](operations.md).

CI runs the version consistency check on pushes and pull requests. Tag pushes additionally validate that the tag matches the application metadata. Release publication remains a maintainer action; pushing a tag does not publish a package to another registry.

## Upgrade an instance

Back up the database and instance encryption keys first. Review the changelog, test the release with isolated integrations, apply migrations, and deploy the new source/image with your existing environment configuration. Verify readiness and representative workflows. Roll back only to application code compatible with the current schema; do not automatically downgrade business data.
