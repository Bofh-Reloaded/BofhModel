The BOfH Model
==============

This is the graph model of token and liquidity swaps.
At the time of wrigin is a C++ implementation that is hosted in a Python module for improved hackability.

All crunching and I/O by Python. Critical algorithms to be implemented in C++.

Requirements
------------

- Some decent C++17 compiler (Using GCC 9)
- Boost
- CMake
- Python 3.8+

How to build
------------

Look at the Dockerfile. It has the complete recipe.


How to run / hack
-----------------

For the fast path using Docker, first time do this:

  docker-compose build 

This takes some time (only the first time) as boost, Python and a other requirements are pulled and built.

Once built, the image can be accessed with:

  docker-compose run --rm bofh_model bash

This start a shell directly in the build directory. 

Sources can be build with

  make && make install

Editing sources OUTSIDE the container does not require its restart. 
The source tree is mounted inside the container in /src. This accomodates live editing and fast roundtrip without rebuilding constantly the docker image, until it's final.


