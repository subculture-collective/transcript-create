#!/usr/bin/env node

/**
 * Custom version updater for standard-version
 * Handles updating version in pyproject.toml files with Python-style version format
 */

const VERSION_REGEX = /(\bversion\s*[:=]\s*['"])([\d.]+[-\w.]*)/;

module.exports.readVersion = function (contents) {
  const match = contents.match(VERSION_REGEX);
  return match ? match[2] : null;
};

module.exports.writeVersion = function (contents, version) {
  return contents.replace(VERSION_REGEX, `$1${version}`);
};
