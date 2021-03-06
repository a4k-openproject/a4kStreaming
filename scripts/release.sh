#!/bin/bash

token=$1
ver=$(echo "$2" | sed "s/release: //")
user="a4k-openproject"
repo="a4kStreaming"
tag_ver="${ver#?}"
tag="plugin.video.a4kstreaming/plugin.video.a4kstreaming-$tag_ver"
api="https://api.github.com/repos/$user/$repo"

generate_release_data()
{
  cat <<EOF
{
  "tag_name": "$tag",
  "name": "$ver"
}
EOF
}

post_data="$(generate_release_data)"

echo "Create release"
echo "$post_data"

curl \
    --header "Authorization: token $token" \
    --header "Accept: application/vnd.github.v3+json" \
    --data "$post_data" \
    "$api/releases"
