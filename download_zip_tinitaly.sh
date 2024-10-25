#!/bin/bash

mkdir -p download_tinitaly

function mywget()
{
	[ -f $(basename "$1") ] || wget --no-check-certificate "$1"
}

function myunzip()
{
	local unpack=true
	if ! unzip -l $1 &>/dev/null
	then
		echo "ERROR: download_tinitaly/$1 seems broken, deleting!"
		rm -f $1
		exit 1
	fi
	for file in $(unzip -l $1 | grep -Po "[^/]+_s10.tif")
	do
		[ ! -f ../tinitaly/$file ] && unpack=true && break
	done

	$unpack && unzip -j -o $1 "*_s10.tif" -d ../tinitaly/
}

export -f mywget myunzip

cd download_tinitaly

#run curl in parallel using 8 thread/connection
xargs -P 8 -I {} bash -c "mywget '{}'" < ../file_list_zip_tinitaly.txt

#unzip the DSM tif files
ls -1 | xargs -P 8 -I {} bash -c "myunzip '{}'"
