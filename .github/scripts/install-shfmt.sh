#!/usr/bin/env bash
set -euo pipefail

readonly SHFMT_VERSION="3.10.0"
readonly SHFMT_SHA256="1f57a384d59542f8fac5f503da1f3ea44242f46dff969569e80b524d64b71dbc"
readonly ARCHIVE="shfmt_v${SHFMT_VERSION}_linux_amd64"

temp_dir=$(mktemp -d)
trap 'rm -rf "${temp_dir}"' EXIT

curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
    "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/${ARCHIVE}" \
    --output "${temp_dir}/${ARCHIVE}"

printf '%s  %s\n' "${SHFMT_SHA256}" "${ARCHIVE}" \
    | (cd "${temp_dir}" && sha256sum --check -)
sudo install -m 0755 "${temp_dir}/${ARCHIVE}" /usr/local/bin/shfmt
