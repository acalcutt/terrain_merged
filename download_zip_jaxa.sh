#!/bin/bash

mkdir -p download_jaxa
CREDENTIALS="USER:PASSWORD"

function mycurl()
{
	URL=$(sed -r "s|(https://)|\1$CREDENTIALS@|" <<<$1)
	[ -f $(basename "$URL") ] || curl -L -O "$URL"
}

function myunzip()
{
	local unpack=true
	if ! unzip -l $1 &>/dev/null
	then
		echo "ERROR: download_jaxa/$1 seems broken, deleting!"
		rm -f $1
		exit 1
	fi
	for file in $(unzip -l $1 | grep -Po "[^/]+_DSM.tif")
	do
		[ ! -f ../jaxa_temp/$file ] && unpack=true && break
	done

	$unpack && unzip -j -o $1 "*_DSM.tif" -d ../jaxa_temp/
}

export -f mycurl myunzip

cd download_jaxa

# run curl in parallel using 8 thread/connection
xargs -P 8 -I {} bash -c "mycurl '{}'" < ../file_list_zip_jaxa.txt

#unzip the DSM tif files
ls -1 | xargs -P 8 -I {} bash -c "myunzip '{}'"
