#!/bin/bash -x

ip="147.99.64.4"

# RSS link as datamatrix
datam="/home/piry/Documents/Labo/PCiEvolBiol/RSS_datamatrix.png"
# echo "http://147.99.65.220:83/PCiEvolBiol/public/rss" | dmtxwrite --encoding=8 --module=4 --output=$datam
echo "http://$ip/PCiEvolBiol/public/rss" | dmtxwrite --encoding=8 --module=4 --output=$datam

# pci-test
unison -auto \
	-ignore "Name *.old" \
	-ignore "Name *.ini" \
	-ignore "Name crontab" \
	-ignore "Name *~" \
	-ignore "Name *.bak" \
	-ignore "Name *.pyc" \
	-ignore "Name *.orig" \
	-ignore "Name .git" \
	-ignore "Name sessions" \
	-ignore "Name errors" \
	-ignore "Name tmp" \
	-ignore "Name *background.png" \
	-ignore "Name *workflow.png" \
	-ignore "Name *datamatrix.*" \
	-ignore "Name *Map.png" \
	-sshargs -C  \
	~/W/web2py_2.17.2/applications/pcidev   ssh://www-data@$ip//home/www-data/web2py_2.17.2/applications/PCiEvolBiol

# echo "UPDATE help_texts SET contents='Details about the process of evaluation & recommendation can be found  [here](../about/help_generic).' WHERE hashtag LIKE '#AcceptPreprintInfoText';" | psql -h $ip -U piry pci_evolbiol_test
# echo "update auth_user set email = lower(email) where email ~ '[A-Z]';"| psql -h $ip -U piry pci_evolbiol_test

# rsopt="--verbose --progress --times"
rsopt="--times --verbose"
rsync $rsopt ~/W/web2py_2.17.2/applications/pcidev/private/appconfig_test.ini      www-data@$ip:/home/www-data/web2py_2.17.2/applications/PCiEvolBiol/private/appconfig.ini
rsync $rsopt /home/piry/W/Labo/PCiEvolBiol/background.png                          www-data@$ip:/home/www-data/web2py_2.17.2/applications/PCiEvolBiol/static/images
rsync $rsopt /home/piry/W/Labo/PCiEvolBiol/images/favicon.*			   www-data@$ip:/home/www-data/web2py_2.17.2/applications/PCiEvolBiol/static/images
rsync $rsopt /home/piry/W/Labo/PCiEvolBiol/small-background.png                    www-data@$ip:/home/www-data/web2py_2.17.2/applications/PCiEvolBiol/static/images
rsync $rsopt /home/piry/W/Labo/PCiEvolBiol/images/Workflow20180314.png             www-data@$ip:/home/www-data/web2py_2.17.2/applications/PCiEvolBiol/static/images
rsync $rsopt $datam                                                                www-data@$ip:/home/www-data/web2py_2.17.2/applications/PCiEvolBiol/static/images

ssh www-data@$ip "find /home/www-data/web2py_2.17.2/applications/PCiEvolBiol -name \\*.pyc -exec rm {} \\; ; touch /home/www-data/web2py_2.17.2/wsgihandler.py"


# Delete local datamatrix
rm -f $datam
