.PHONY: vendor build run clean

SANTRICITY_CLIENT_REPO ?= https://github.com/scaleoutsean/santricity-client.git
SANTRICITY_CLIENT_VERSION ?= 0.2.6
SANTRICITY_DEST = epa/santricity_client

all: vendor build

vendor:
	@echo "Vendoring SANtricity client to $(SANTRICITY_DEST)..."
	rm -rf /tmp/santricity-client-tmp
	git clone --depth 1 -b $(SANTRICITY_CLIENT_VERSION) $(SANTRICITY_CLIENT_REPO) /tmp/santricity-client-tmp
	mkdir -p $(SANTRICITY_DEST)
	cp -r /tmp/santricity-client-tmp/src/santricity_client/* $(SANTRICITY_DEST)/
	rm -rf /tmp/santricity-client-tmp
	@echo "Vendoring complete."

build: vendor
	docker compose build

run:
	docker compose up -d

clean:
	rm -rf $(SANTRICITY_DEST)
