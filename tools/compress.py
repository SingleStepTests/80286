#!/usr/bin/env python3

# MIT License
#
# Copyright (c) 2025 Daniel Balsom
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import sys
import gzip
import shutil

def gzip_files_in_directory(dir_path):
    if not os.path.isdir(dir_path):
        print(f"Error: {dir_path} is not a directory or doesn't exist.")
        return

    for filename in os.listdir(dir_path):

        if filename == "metadata.json" or filename == "readme.md":
            continue

        filepath = os.path.join(dir_path, filename)

        # Skip if it's a directory or already gzipped
        if os.path.isdir(filepath) or filename.endswith('.gz'):
            continue

        gzipped_path = filepath + '.gz'

        with open(filepath, 'rb') as f_in:
            with gzip.open(gzipped_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        print(f"Gzipped {filename} -> {filename}.gz")

def main():
    if len(sys.argv) != 2:
        print("Usage: python compress.py <directory_path>")
        sys.exit(1)

    directory = sys.argv[1]
    gzip_files_in_directory(directory)

if __name__ == "__main__":
    main()