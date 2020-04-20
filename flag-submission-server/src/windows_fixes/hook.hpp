// g++ -fpic -shared -O2 -std=c++11 prototype1.cpp -o prototype1.so -ldl && nm prototype1.so | grep -e 'puts' -e 'gets' -e 'printf'
#ifndef HOOK
#define HOOK


#include <dlfcn.h>
#include <stdarg.h>
#include <stdio.h>

// A "simple" function pointer - macro compatible
template<typename FT> class FuncPtr{
public:
	FT* ptr;
	inline explicit FuncPtr(FT* ptr) : ptr(ptr){}
	inline FuncPtr(int, const char* name){
		ptr = (FT*) dlsym(RTLD_NEXT, name);
		// printf("Resolved %s to %p, stored at %p in class %p...\n", name, ptr, &ptr, this);
	}
};

// Load a hookable function from another library
#define real_function(name, type) \
	FuncPtr<type> real_##name(0, #name)


#ifdef __x86_64__
// === x86-64 (64 bit) ===

// Install a hook into a previously loaded real function
// According to all x64 calling conventions, r11 is caller-saved and not used as parameter-passing register
#define install_hook(name, hook)                                        \
	void* hook_ptr_##name = (void*) &(hook);                             \
	__asm__ __volatile__ (".text\n"                                       \
			".global " #name "\n"                                          \
			".type   " #name ", @function\n"                                \
			#name ":\n"                                                      \
			"movq hook_ptr_" #name "@GOTPCREL(%rip), %r11; \n"                \
			"jmp *(%r11)\n"                                                    \
			".data\n");

#else
#ifdef __i386__
// === x86 (32 bit) ===
	
// Install a hook into a previously loaded real function
#define install_hook(name, hook)                                  \
	void* hook_ptr_##name = (void*) &hook;                         \
	__asm__ __volatile__ (".text\n"                                 \
			".global " #name "\n"                                    \
			".type   " #name ", @function\n"                          \
			#name ":\n"                                                \
			"pushl %ebx \n"                                             \
			"call __x86.get_pc_thunk.bx \n"                              \
			"addl $_GLOBAL_OFFSET_TABLE_, %ebx \n"                        \
			"movl hook_ptr_" #name "@GOT(%ebx), %ebx \n"                   \
			"movl (%ebx), %ebx \n"                                          \
			"movl %ebx, -4(%esp) \n"                                         \
			"popl %ebx \n"                                                    \
			"jmp *-8(%esp) \n"                                                 \
			".data\n");

#else

#error Unknown architecture!

#endif
#endif




// resolve the real, unpatched function
#define real(name) (*real_##name.ptr)

#endif
