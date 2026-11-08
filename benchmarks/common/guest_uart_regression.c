#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/reent.h>

extern int _write_r(struct _reent *r, int file, char *ptr, int len);

static void guest_exit(void)
{
    // ARM32 passes the uint64_t nanosecond delay in r0:r1. Clear both words.
    __asm__ __volatile__ (
        "mov r0, #0; mov r1, #0; .inst 0xEE000110 | (0x21 << 16);"
        :
        :
        : "r0", "r1", "memory");
}

void isr(void) {
}

int main(void) {
    struct _reent custom_reent;
    memset(&custom_reent, 0, sizeof(custom_reent));

    // Case 1: Trailing canary buffer - only first 9 bytes must be printed.
    char canary_buf[] = {'[', 'T', 'E', 'S', 'T', '_', 'O', 'K', ']', 'C', 'A', 'N', 'A', 'R', 'Y'};
    int ret1 = _write_r(&custom_reent, 1, canary_buf, 9);
    if (ret1 != 9 || custom_reent._errno != 0) {
        printf("\nFAIL_CASE_1: ret=%d, errno=%d\n", ret1, custom_reent._errno);
        guest_exit();
        return 1;
    }

    // Case 2: Embedded NUL byte across requested length.
    char nul_buf[] = {'[', 'N', 'U', 'L', 0, 'O', 'K', ']'};
    int ret2 = _write_r(&custom_reent, 1, nul_buf, 8);
    if (ret2 != 8 || custom_reent._errno != 0) {
        printf("\nFAIL_CASE_2: ret=%d, errno=%d\n", ret2, custom_reent._errno);
        guest_exit();
        return 2;
    }

    // Case 3: Zero length on valid and invalid/null pointers.
    int ret3a = _write_r(&custom_reent, 1, NULL, 0);
    int ret3b = _write_r(&custom_reent, 1, (char *)0x1, 0);
    if (ret3a != 0 || ret3b != 0 || custom_reent._errno != 0) {
        printf("\nFAIL_CASE_3: ret3a=%d, ret3b=%d\n", ret3a, ret3b);
        guest_exit();
        return 3;
    }

    // Case 4: Negative length reports EINVAL.
    custom_reent._errno = 0;
    errno = 0;
    int ret4 = _write_r(&custom_reent, 1, canary_buf, -1);
    if (ret4 != -1 || custom_reent._errno != EINVAL || errno != EINVAL) {
        printf("\nFAIL_CASE_4: ret=%d, r_errno=%d, errno=%d\n", ret4, custom_reent._errno, errno);
        guest_exit();
        return 4;
    }

    // Case 5: Null pointer with positive length reports EFAULT.
    custom_reent._errno = 0;
    errno = 0;
    int ret5 = _write_r(&custom_reent, 1, NULL, 5);
    if (ret5 != -1 || custom_reent._errno != EFAULT || errno != EFAULT) {
        printf("\nFAIL_CASE_5: ret=%d, r_errno=%d, errno=%d\n", ret5, custom_reent._errno, errno);
        guest_exit();
        return 5;
    }

    printf("\nGUEST_UART_CONTRACT_PASSED\n");
    guest_exit();
    return 0;
}
