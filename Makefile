# Makefile for Blockchain Paxos Project

PYTHON = python3
SHELL := /bin/bash

.PHONY: all start stop clean help p1 p2 p3 p4 p5

all: help

help:
	@echo "Blockchain Paxos Commands:"
	@echo "  make start   - Start all 5 processes + master"
	@echo "  make stop    - Stop all processes"
	@echo "  make clean   - Remove blockchain files"
	@echo ""
	@echo "Individual processes (foreground):"
	@echo "  make p1, p2, p3, p4, p5"

# Start all processes + master
start:
	@mkdir -p logs
	@echo "Starting all processes..."
	$(PYTHON) p1.py > logs/p1.log 2>&1 & echo $$! > .p1.pid
	$(PYTHON) p2.py > logs/p2.log 2>&1 & echo $$! > .p2.pid
	$(PYTHON) p3.py > logs/p3.log 2>&1 & echo $$! > .p3.pid
	$(PYTHON) p4.py > logs/p4.log 2>&1 & echo $$! > .p4.pid
	$(PYTHON) p5.py > logs/p5.log 2>&1 & echo $$! > .p5.pid
	@sleep 2
	@echo "✅ All processes started"
	@echo "View logs: tail -f logs/p1.log"
	@echo ""
	@echo "Starting master..."
	@$(PYTHON) master.py

# Stop all processes
stop:
	@echo "Stopping all processes..."
	@-kill `cat .p1.pid` 2>/dev/null && rm .p1.pid && echo "P1 stopped" || true
	@-kill `cat .p2.pid` 2>/dev/null && rm .p2.pid && echo "P2 stopped" || true
	@-kill `cat .p3.pid` 2>/dev/null && rm .p3.pid && echo "P3 stopped" || true
	@-kill `cat .p4.pid` 2>/dev/null && rm .p4.pid && echo "P4 stopped" || true
	@-kill `cat .p5.pid` 2>/dev/null && rm .p5.pid && echo "P5 stopped" || true
	@echo "✅ All processes stopped"

# Individual processes (foreground)
p1:
	@$(PYTHON) p1.py

p2:
	@$(PYTHON) p2.py

p3:
	@$(PYTHON) p3.py

p4:
	@$(PYTHON) p4.py

p5:
	@$(PYTHON) p5.py

# Clean blockchain files
clean: stop
	@rm -f p1.json p2.json p3.json p4.json p5.json
	@rm -f .p*.pid
	@rm -rf logs
	@echo "✅ Cleaned"