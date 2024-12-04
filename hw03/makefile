VENV := .venv/bin

main:
	make clean
	mkdir -p games-ca978112
	cp games/rps.py games-ca978112/rps.py
	mkdir -p games-3e23e816
	cp games/ttt.py games-3e23e816/ttt.py
	$(VENV)/python server.py

clean:
	rm -f *.log *.json
	rm -rf games-*
	rm -rf __pycache__