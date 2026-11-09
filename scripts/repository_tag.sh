#!/bin/bash
# Tags the repository add-on for Kodi: at each version bump of packages/repository.a4kstreaming/addon.xml, after that
# commit, run this locally. Kodi fetches <datadir>/repository.a4kstreaming/repository.a4kstreaming-<version>.zip, which
# GitHub serves as the archive of the ref repository.a4kstreaming/repository.a4kstreaming-<version>. The tag points at
# a parentless commit whose tree root is the add-on itself (HEAD's packages/repository.a4kstreaming/). Never pushes.

set -eu
export TZ=UTC

want='newt-sc <47229722+newt-sc@users.noreply.github.com>'
src=packages/repository.a4kstreaming

cd "$(git rev-parse --show-toplevel)"

for who in AUTHOR COMMITTER; do
  ident=$(git var "GIT_${who}_IDENT")
  if [ "${ident% * *}" != "$want" ]; then
    echo "refusing: $who is '${ident% * *}', want '$want'" >&2; exit 1
  fi
done

if ! git diff --quiet HEAD -- "$src" || [ -n "$(git ls-files --others --exclude-standard -- "$src")" ]; then
  echo "refusing: $src differs from HEAD; commit it first" >&2; exit 1
fi

ver=$(git show "HEAD:$src/addon.xml" | tail -n +2 | grep -o 'version="[^"]*"' | head -n 1 | cut -d '"' -f 2)
[ -n "$ver" ] || { echo "refusing: no version in $src/addon.xml" >&2; exit 1; }
tag="repository.a4kstreaming/repository.a4kstreaming-$ver"
if git rev-parse -q --verify "refs/tags/$tag" > /dev/null; then
  echo "refusing: tag $tag exists" >&2; exit 1
fi

tree=$(git rev-parse "HEAD:$src")
commit=$(git commit-tree "$tree" -m "repository.a4kstreaming $ver")
git tag "$tag" "$commit"

echo "tagged $tag -> $commit"
git ls-tree "$tag"
echo "push refs/tags/$tag to the add-on's remote"
