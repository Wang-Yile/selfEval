ARGS = -std=c++17 -Wall -Wextra -Wshadow -Wconversion -O2

all: sandbox sandbox-tiny

sandbox: sandbox.cpp sandbox.h
	g++ sandbox.cpp -o sandbox $(ARGS) -lseccomp
sandbox-tiny: sandbox-tiny.cpp sandbox.h
	g++ sandbox-tiny.cpp -o sandbox-tiny $(ARGS)
