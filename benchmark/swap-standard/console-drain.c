// SPDX-License-Identifier: GPL-2.0-only
/* Wait for serial output before the guest powers off. */
#include <stdio.h>
#include <termios.h>
#include <unistd.h>

int main(void)
{
    if (tcdrain(STDOUT_FILENO)) {
        perror("tcdrain");
        return 1;
    }
    return 0;
}
