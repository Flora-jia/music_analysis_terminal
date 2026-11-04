/* Keep the original GLIBC <=2.27 deployment floor. No algorithm source edits. */
#if defined(__arm__) && defined(__linux__)
__asm__(".symver log2,log2@GLIBC_2.4");
#endif
