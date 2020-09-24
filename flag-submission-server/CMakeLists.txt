cmake_minimum_required(VERSION 3.11)
project(flag-submission-server)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -flto")
set(CMAKE_CXX_FLAGS_MINSIZEREL "-Os -flto")


# WSL (Windows Subsystem for Linux) hacks
EXEC_PROGRAM(uname ARGS -r OUTPUT_VARIABLE UNAME_RESULT)
if ("${UNAME_RESULT}" MATCHES "Microsoft")
	message("Kernel ${UNAME_RESULT}, WSL fixes enabled")
	set(SOURCE_FILES_FIX src/windows_fixes/fixes.cpp src/windows_fixes/hook.hpp)
	set(FIX_LIBRARIES dl)
else ("${UNAME_RESULT}" MATCHES "Microsoft")
endif ("${UNAME_RESULT}" MATCHES "Microsoft")


# configure clang's sanitizers (build with -DCMAKE_BUILD_TYPE=addrsanitizer / memsanitizer)
SET(CMAKE_C_FLAGS_ADDRSANITIZER "-fsanitize=address -fsanitize=undefined -fno-omit-frame-pointer -fno-optimize-sibling-calls -O1 -g")
SET(CMAKE_CXX_FLAGS_ADDRSANITIZER "-fsanitize=address -fsanitize=undefined -fno-omit-frame-pointer -fno-optimize-sibling-calls -O1 -g")
SET(CMAKE_C_FLAGS_THREADSANITIZER "-fsanitize=thread -fsanitize=undefined -fno-omit-frame-pointer -fno-optimize-sibling-calls -O1 -g")
SET(CMAKE_CXX_FLAGS_THREADSANITIZER "-fsanitize=thread -fsanitize=undefined -fno-omit-frame-pointer -fno-optimize-sibling-calls -O1 -g")
IF (${CMAKE_BUILD_TYPE} STREQUAL "addrsanitizer" OR ${CMAKE_BUILD_TYPE} STREQUAL "threadsanitizer")
	message("--- SANITIZER BUILD CONFIGURED ---")
	set(CMAKE_C_COMPILER clang)
	set(CMAKE_CXX_COMPILER clang++)
ENDIF (${CMAKE_BUILD_TYPE} STREQUAL "addrsanitizer" OR ${CMAKE_BUILD_TYPE} STREQUAL "threadsanitizer")


set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} ${CMAKE_SOURCE_DIR}/cmake)
find_package(Libev REQUIRED)
include_directories(${LIBEV_INCLUDE_DIRS})
find_package(LibHiredis REQUIRED)
include_directories(${LIBHIREDIS_INCLUDE_DIRS})
find_package(OpenSSL 1.1 REQUIRED)
include_directories(${OPENSSL_INCLUDE_DIRS})
find_package(PostgreSQL REQUIRED)
include_directories(${PostgreSQL_INCLUDE_DIRS})


# Download JSON library
include(FetchContent)
#FetchContent_Declare(json GIT_REPOSITORY https://github.com/nlohmann/json.git GIT_TAG v3.7.3)
FetchContent_Declare(json GIT_REPOSITORY https://github.com/ArthurSonzogni/nlohmann_json_cmake_fetchcontent.git GIT_TAG v3.9.1)
FetchContent_GetProperties(json)
if (NOT json_POPULATED)
	FetchContent_Populate(json)
	add_subdirectory(${json_SOURCE_DIR} ${json_BINARY_DIR} EXCLUDE_FROM_ALL)
	message("Retrieved nlohmann::json to \"${json_SOURCE_DIR}\"")
	include_directories("${json_SOURCE_DIR}/include")
endif ()


set(SOURCE_FILES
		src/flagchecker.cpp
		src/flagchecker.h
		src/database.cpp
		src/database.h
		src/workerpool.cpp
		src/workerpool.h
		src/flagcache.cpp
		src/flagcache.h
		src/config.cpp
		src/config.h
		src/redis.cpp
		src/redis.h
		src/libraries/base64.h
		src/libraries/base64.c
		src/statistics.cpp
		src/statistics.h
		)
set(SOURCE_FILES ${SOURCE_FILES} ${SOURCE_FILES_FIX})
add_executable(flag-submission-server ${SOURCE_FILES} src/main.cpp)
target_link_libraries(flag-submission-server ${CMAKE_THREAD_LIBS_INIT} ${LIBEV_LIBRARIES} ${OPENSSL_CRYPTO_LIBRARY} ${PostgreSQL_LIBRARIES} ${LIBHIREDIS_LIBRARIES} ${FIX_LIBRARIES})


set(SOURCE_FILES_2 benchmark/benchmark_oldflags.cpp)
add_executable(benchmark-oldflags ${SOURCE_FILES_2})


set(SOURCE_FILES_3
		benchmark/benchmark_newflags.cpp
		src/flagchecker.cpp
		src/flagcache.cpp
		src/config.cpp
		src/libraries/base64.h
		src/libraries/base64.c
		)
add_executable(benchmark-newflags ${SOURCE_FILES_3})
target_link_libraries(benchmark-newflags ${OPENSSL_CRYPTO_LIBRARY})


set(SOURCE_FILES_TEST
		tests/test_main.cpp
		)
add_library(Catch INTERFACE)
add_executable(testsuite ${SOURCE_FILES_TEST} ${SOURCE_FILES})
target_link_libraries(testsuite Catch ${CMAKE_THREAD_LIBS_INIT} ${LIBEV_LIBRARIES} ${OPENSSL_CRYPTO_LIBRARY} ${PostgreSQL_LIBRARIES} ${LIBHIREDIS_LIBRARIES})
