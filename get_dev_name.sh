#!/bin/bash -e

DEVNAME=$(aplay -l | grep Yeti | cut -d':' -f2 | cut -d'[' -f1 | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
echo Device Name:  $DEVNAME

#SERVERIP=$(ifconfig | grep -E 'inet.[0-9]' | grep -v '127.0.0.1' | awk '{ print $2 }')
SERVERIP=$(ip route get 8.8.8.8 | awk -F"src " 'NR==1{split($2,a," ");print a[1]}')
echo Server IP:  $SERVERIP

CLIENTIP=$(echo $SERVERIP | cut -d '.' -f 1-3).255  ## Broadcast to all on subnet/LAN
echo Client IP:  $CLIENTIP

