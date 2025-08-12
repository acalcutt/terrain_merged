#!/bin/bash

mkdir -p opendtm_de

function mywget()
{
	[ -f $(basename "$1") ] || wget --no-check-certificate "$1"
}

function myunzip()
{
	if ! command -v unzip &>/dev/null
	then
		echo "ERROR: unzip is not installed, please install it to continue."
		exit 1
	fi

	local unpack=true
	if ! unzip -l $1 &>/dev/null
	then
		echo "ERROR: opendtm_de/$1 seems broken, deleting!"
		rm -f $1
		exit 1
	fi
	for file in $(unzip -l $1 | grep -Po "[^/]+.tif")
	do
		[ ! -f ../opendtm_de/$file ] && unpack=true && break
	done

	$unpack && unzip -j -o $1 "*.tif" -d ../opendtm_de/
}

export -f mywget myunzip

cd opendtm_de

# download serially, as requested by the opendem.info website.
xargs -I {} bash -c "mywget '{}'" < ../file_list_zip_opendtm.txt

# unzip the DSM tif files
ls -1 *.zip | xargs -P 8 -I {} bash -c "myunzip '{}'"
