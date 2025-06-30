# 80286
A Hardware-Generated CPU Test Suite for the Intel 80286

This repository will eventually contain CPU tests for the 80286.
Progress in controlling an 80286 with an Arduino Giga is very promising, and we are able to load and store the CPU state with the LOADALL and STOREALL instructions.

The first phase will be a release of real mode tests. 

Protected mode tests should be possible as well but may be a little tricky, as we want to randomize segment descriptors without making the vast majority of tests end up in a fault condition. 

![image](https://github.com/user-attachments/assets/71d0204c-5497-40b3-ae03-2486dcc72722)
