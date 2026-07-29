CC ?= gcc
CFLAGS ?= -O3 -std=c17 -Wall -Wextra -Wpedantic
CPPFLAGS ?= -Isrc
LDLIBS ?= -lm

TARGET := build/fractal-renderer
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
	SHARED := build/libbifurcation.dylib
	SHARED_LDFLAGS := -dynamiclib
else
	SHARED := build/libbifurcation.so
	SHARED_LDFLAGS := -shared
endif

CLI_SOURCES := src/main.c src/fractal.c src/palette.c
LIB_SOURCES := src/fractal.c src/palette.c src/numeric.c src/internal_curves.c
HEADERS := src/fractal.h src/palette.h src/numeric.h src/numeric_internal.h

OPENMP_SUPPORTED := $(shell printf 'int main(void){return 0;}\n' | \
	$(CC) -x c -fopenmp -o /tmp/bifurcation-loom-openmp-test - >/dev/null 2>&1 && echo yes)
ifeq ($(OPENMP_SUPPORTED),yes)
	CFLAGS += -fopenmp
	LDLIBS += -fopenmp
endif

.PHONY: all clean run test

all: $(TARGET) $(SHARED)

$(TARGET): $(CLI_SOURCES) $(HEADERS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(CLI_SOURCES) -o $@ $(LDLIBS)

$(SHARED): $(LIB_SOURCES) $(HEADERS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) -fPIC $(SHARED_LDFLAGS) $(LIB_SOURCES) -o $@ $(LDLIBS)

build:
	mkdir -p $@

run: all
	python3 app.py

test: all
	python3 -m unittest discover -s tests -v

clean:
	rm -f $(TARGET) build/libbifurcation.so build/libbifurcation.dylib
