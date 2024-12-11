#!/bin/bash

mkdir -p download_france

function mywget()
{
	[ -f $(basename "$1") ] || wget --no-check-certificate "$1"
}

function myunzip()
{
	7za -y x $1
}

export -f mywget myunzip

cd download_france

# run wget in parallel using 8 thread/connection
xargs -P 8 -n 1 -I {} bash -c "mywget '{}'" < ../file_list_france_5m.txt

find . -maxdepth 1 -type f | xargs -P 8 -I {} bash -c "myunzip '{}'"
