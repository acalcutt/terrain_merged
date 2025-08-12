#!/bin/bash

mkdir -p italy_sudtirol

function mywget()
{
	[ -f $(basename "$1") ] || wget --no-check-certificate "$1"
}

export -f mywget

cd italy_sudtirol

# Download files and rename them based on line number
awk '{print NR, $0}' ../file_list_tif_sudtirol.txt | xargs -P 8 -n 2 bash -c '
	url="$1"
	num="$0"
	outfile="${num}.tif"
	[ -f "$outfile" ] || wget --no-check-certificate -O "$outfile" "$url"
' 
