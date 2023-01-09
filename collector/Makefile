SHELL := bash
.PHONY: help build

tag='ntap-grafana-plugin/eseries_monitoring'
apps=collector dbmanager
$(shell cat config.json > ./dbmanager/config.json)

build:
	for a in collector dbmanager; do echo "Building $${a} in `pwd` \n" && docker build -t ${tag}/"$${a}" -f `pwd`/"$${a}"/Dockerfile `pwd`/"$${a}"; done

