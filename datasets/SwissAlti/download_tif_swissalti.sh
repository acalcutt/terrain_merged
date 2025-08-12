#!/bin/bash

mkdir -p swissalti

function mywget()
{
	[ -f $(basename "$1") ] || wget --no-check-certificate "$1"
}

export -f mywget

cd swissalti

# run wget in parallel using 8 thread/connection
xargs -P 8 -I {} bash -c "mywget '{}'" < ../file_list_tif_swissalti.txt
