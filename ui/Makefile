UIS := $(wildcard *.ui)
PYS := $(patsubst %.ui, %.py, ${UIS})

all: ${PYS}

%.py: %.ui
	uic -g python $< -o $@