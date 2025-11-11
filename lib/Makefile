ARGS = -std=c++17 -Wall -Wextra -Wshadow -Wconversion -O3

all: sandbox sandbox-tiny

sandbox: Makefile sandbox.cpp sandbox.h
	g++ sandbox.cpp -o sandbox $(ARGS) -lseccomp
sandbox-tiny: Makefile sandbox-tiny.cpp sandbox.h
	g++ sandbox-tiny.cpp -o sandbox-tiny $(ARGS)
