#!/bin/bash
CWD="${PWD}/"
SYSREQFILE="${CWD}requirements.system"
if [[ -f $SYSREQFILE ]]; then
	# cat $SYSREQFILE | xargs sudo apt-get install -y 
	if xargs sudo apt-get --ignore-missing install -y < $SYSREQFILE ; then
		echo -e "\nxargs batch install successful.\n"
	else
		echo -e "\nxargs batch install failed -- using iterative approach instead...\n"
		while IFS="" read -r p || [ -n "$p" ]; do
			sudo apt-get install -y $p 
			echo 
		done < $SYSREQFILE
	fi
else
	echo -e "\nSystem (apt-get) requirements file '$SYSREQFILE' not found.\n  -->  Skipping apt dependency installations.\n"
fi
PIPREQFILE="${CWD}requirements.txt"
if [[ -f $PIPREQFILE ]]; then
	# pip3 install -r $PIPREQFILE
	python3.7 -m pip install --user -r $PIPREQFILE
else
	echo -e "\nPython3 (pip3) requirements file '$PIPREQFILE' not found.\n  -->  Skipping pip dependency installations.\n"
fi