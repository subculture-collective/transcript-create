#!/usr/bin/env node

/**
 * Custom version updater for standard-version
 * Handles updating version in pyproject.toml and package.json files
 */

const fs = require('fs');
const path = require('path');

const PLAIN_TEXT_BUMP_FILES = ['pyproject.toml'];
const JSON_BUMP_FILES = ['frontend/package.json', 'clients/javascript/package.json', 'e2e/package.json'];

const VERSION_REGEX = /(\bversion\s*[:=]\s*['"])([\d.]+[-\w.]*)/;

module.exports.readVersion = function (contents) {
  const match = contents.match(VERSION_REGEX);
  return match ? match[2] : null;
};

module.exports.writeVersion = function (contents, version) {
  return contents.replace(VERSION_REGEX, `$1${version}`);
};
