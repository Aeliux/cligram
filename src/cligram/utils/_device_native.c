/*
 * Native device detection module for cligram
 * High-performance platform detection using compile-time checks and native APIs
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>

/* Compile-time platform detection */
#if defined(_WIN32) || defined(_WIN64)
    #define PLATFORM_WINDOWS 1
    #include <windows.h>
    #pragma comment(lib, "advapi32.lib")
#elif defined(__ANDROID__)
    #define PLATFORM_ANDROID 1
    #include <sys/system_properties.h>
    #include <unistd.h>
#elif defined(__APPLE__)
    #include <TargetConditionals.h>
    #if TARGET_OS_MAC
        #define PLATFORM_MACOS 1
        #include <sys/sysctl.h>
        #include <sys/utsname.h>
    #endif
#elif defined(__linux__)
    #define PLATFORM_LINUX 1
    #include <sys/utsname.h>
    #include <unistd.h>
#endif

/* Architecture detection */
#if defined(__x86_64__) || defined(_M_X64) || defined(__amd64__)
    #define ARCH_X64 1
    #define ARCH_STRING "x64"
#elif defined(__i386__) || defined(_M_IX86) || defined(__i386)
    #define ARCH_X86 1
    #define ARCH_STRING "x86"
#elif defined(__aarch64__) || defined(_M_ARM64) || defined(__arm64__)
    #define ARCH_ARM64 1
    #define ARCH_STRING "arm64"
#elif defined(__arm__) || defined(_M_ARM) || defined(__arm)
    #define ARCH_ARM 1
    #define ARCH_STRING "arm"
#else
    #define ARCH_UNKNOWN 1
    #define ARCH_STRING "unknown"
#endif

#define MAX_BUFFER 512

/* Environment detection flags */
typedef enum {
    ENV_LOCAL = 1 << 0,
    ENV_DOCKER = 1 << 1,
    ENV_ACTIONS = 1 << 2,
    ENV_CODESPACES = 1 << 3,
    ENV_VIRTUAL_MACHINE = 1 << 4,
    ENV_WSL = 1 << 5,
    ENV_TERMUX = 1 << 6
} EnvironmentFlags;

/* Helper function to safely read a file */
static int read_file_safe(const char* filepath, char* buffer, size_t buffer_size) {
    FILE* fp = fopen(filepath, "r");
    if (!fp) return 0;

    size_t bytes_read = fread(buffer, 1, buffer_size - 1, fp);
    buffer[bytes_read] = '\0';
    fclose(fp);

    /* Remove trailing whitespace and null bytes */
    while (bytes_read > 0 && (buffer[bytes_read - 1] == '\n' ||
                               buffer[bytes_read - 1] == '\r' ||
                               buffer[bytes_read - 1] == '\0' ||
                               buffer[bytes_read - 1] == ' ')) {
        buffer[--bytes_read] = '\0';
    }

    return bytes_read > 0;
}

/* Detect runtime environment */
static int detect_environments(void) {
    int flags = 0;

    /* Check for Docker/Container */
    #ifdef PLATFORM_WINDOWS
    /* On Windows, check if running in Docker by checking environment variables */
    if (getenv("DOCKER_HOST") || getenv("container")) {
        flags |= ENV_DOCKER;
    }
    #else
    /* On Unix-like systems, check for container marker files */
    FILE* fp = fopen("/.dockerenv", "r");
    if (fp) {
        fclose(fp);
        flags |= ENV_DOCKER;
    } else {
        fp = fopen("/.containerenv", "r");
        if (fp) {
            fclose(fp);
            flags |= ENV_DOCKER;
        }
    }
    #endif

    /* Check environment variables */
    if (getenv("CODESPACES")) {
        flags |= ENV_CODESPACES;
    }
    if (getenv("GITHUB_ACTIONS")) {
        flags |= ENV_ACTIONS;
    }
    if (getenv("WSL_DISTRO_NAME")) {
        flags |= ENV_WSL;
    }
    if (getenv("TERMUX_VERSION")) {
        flags |= ENV_TERMUX;
    }

    /* Default to local if no special environment detected */
    if (flags == 0) {
        flags = ENV_LOCAL;
    }

    return flags;
}

/* Convert environment flags to Python list */
static PyObject* environments_to_list(int env_flags) {
    PyObject* env_list = PyList_New(0);
    if (!env_list) return NULL;

    const char* env_names[] = {
        "Local", "Docker", "GitHub Actions", "Github Codespaces",
        "Virtual Machine", "WSL", "Termux"
    };

    for (int i = 0; i < 7; i++) {
        if (env_flags & (1 << i)) {
            PyObject* env_str = PyUnicode_FromString(env_names[i]);
            if (!env_str) {
                Py_DECREF(env_list);
                return NULL;
            }
            PyList_Append(env_list, env_str);
            Py_DECREF(env_str);
        }
    }

    return env_list;
}

#ifdef PLATFORM_WINDOWS
/* RtlGetVersion for accurate Windows version detection */
typedef LONG (WINAPI* RtlGetVersionPtr)(PRTL_OSVERSIONINFOW);

/* Map Windows NT version to marketing version */
static void get_windows_marketing_version(DWORD major, DWORD minor, DWORD build, char* version) {
    if (major == 10) {
        if (build >= 22000) {
            strncpy(version, "11", MAX_BUFFER - 1);
        } else {
            strncpy(version, "10", MAX_BUFFER - 1);
        }
    } else if (major == 6) {
        if (minor == 3) {
            strncpy(version, "8.1", MAX_BUFFER - 1);
        } else if (minor == 2) {
            strncpy(version, "8", MAX_BUFFER - 1);
        } else if (minor == 1) {
            strncpy(version, "7", MAX_BUFFER - 1);
        } else if (minor == 0) {
            strncpy(version, "Vista", MAX_BUFFER - 1);
        }
    } else if (major == 5) {
        if (minor == 1) {
            strncpy(version, "XP", MAX_BUFFER - 1);
        } else if (minor == 0) {
            strncpy(version, "2000", MAX_BUFFER - 1);
        }
    } else {
        /* Unknown version, show NT version */
        snprintf(version, MAX_BUFFER, "NT %lu.%lu", major, minor);
    }
    version[MAX_BUFFER - 1] = '\0';
}

/* Windows-specific detection */
static int get_windows_info(char* name, char* version, char* model) {
    strcpy(name, "Windows");

    /* Get accurate Windows version using RtlGetVersion */
    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    if (ntdll) {
        RtlGetVersionPtr RtlGetVersion = (RtlGetVersionPtr)GetProcAddress(ntdll, "RtlGetVersion");
        if (RtlGetVersion) {
            RTL_OSVERSIONINFOW osvi;
            ZeroMemory(&osvi, sizeof(RTL_OSVERSIONINFOW));
            osvi.dwOSVersionInfoSize = sizeof(RTL_OSVERSIONINFOW);

            if (RtlGetVersion(&osvi) == 0) {
                get_windows_marketing_version(osvi.dwMajorVersion, osvi.dwMinorVersion,
                                             osvi.dwBuildNumber, version);
            } else {
                strcpy(version, "Unknown");
            }
        } else {
            strcpy(version, "Unknown");
        }
    } else {
        strcpy(version, "Unknown");
    }

    /* Get system model from registry */
    HKEY hKey;
    DWORD dwType = REG_SZ;
    DWORD dwSize = MAX_BUFFER;

    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,
                      "HARDWARE\\DESCRIPTION\\System\\BIOS",
                      0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        if (RegQueryValueExA(hKey, "SystemProductName", NULL, &dwType,
                            (LPBYTE)model, &dwSize) != ERROR_SUCCESS) {
            /* Fallback to computer name */
            DWORD size = MAX_BUFFER;
            if (!GetComputerNameA(model, &size)) {
                strcpy(model, "Unknown");
            }
        }
        RegCloseKey(hKey);
    } else {
        /* Fallback to computer name */
        DWORD size = MAX_BUFFER;
        if (!GetComputerNameA(model, &size)) {
            strcpy(model, "Unknown");
        }
    }

    return 1;
}
#endif

#ifdef PLATFORM_LINUX
/* Linux-specific detection */
static int get_linux_distro_info(char* name, char* version) {
    strcpy(name, "Linux");
    strcpy(version, "Unknown");

    FILE* fp = fopen("/etc/os-release", "r");
    if (!fp) return 0;

    char line[MAX_BUFFER];
    while (fgets(line, sizeof(line), fp)) {
        if (strncmp(line, "NAME=", 5) == 0) {
            char* value = line + 5;
            /* Remove quotes and newline */
            if (*value == '"') value++;
            size_t len = strlen(value);
            if (len > 0 && value[len-1] == '\n') value[--len] = '\0';
            if (len > 0 && value[len-1] == '"') value[--len] = '\0';
            strncpy(name, value, MAX_BUFFER - 1);
        } else if (strncmp(line, "VERSION_ID=", 11) == 0) {
            char* value = line + 11;
            if (*value == '"') value++;
            size_t len = strlen(value);
            if (len > 0 && value[len-1] == '\n') value[--len] = '\0';
            if (len > 0 && value[len-1] == '"') value[--len] = '\0';
            strncpy(version, value, MAX_BUFFER - 1);
        }
    }

    fclose(fp);
    return 1;
}

static int get_linux_model(char* model) {
    const char* dmi_paths[] = {
        "/sys/class/dmi/id/product_name",
        "/sys/class/dmi/id/board_name",
        "/sys/devices/virtual/dmi/id/product_name",
        NULL
    };

    /* Try DMI information first */
    for (int i = 0; dmi_paths[i] != NULL; i++) {
        if (read_file_safe(dmi_paths[i], model, MAX_BUFFER)) {
            /* Filter out placeholder values */
            if (strcasecmp(model, "To be filled by O.E.M.") != 0 &&
                strcasecmp(model, "Default string") != 0 &&
                strcasecmp(model, "System Product Name") != 0) {
                return 1;
            }
        }
    }

    /* Try device tree for ARM devices */
    const char* dt_paths[] = {
        "/proc/device-tree/model",
        "/sys/firmware/devicetree/base/model",
        NULL
    };

    for (int i = 0; dt_paths[i] != NULL; i++) {
        if (read_file_safe(dt_paths[i], model, MAX_BUFFER)) {
            return 1;
        }
    }

    /* Fallback to hostname */
    if (gethostname(model, MAX_BUFFER) == 0) {
        return 1;
    }

    strcpy(model, "Unknown");
    return 0;
}
#endif

#ifdef PLATFORM_ANDROID
/* Android-specific detection */
static int get_android_property(const char* key, char* value, size_t value_size) {
    return __system_property_get(key, value) > 0;
}

static int get_android_info(char* name, char* version, char* model) {
    strcpy(name, "Android");

    char release[MAX_BUFFER] = {0};
    char sdk[MAX_BUFFER] = {0};

    /* Get Android version */
    if (get_android_property("ro.build.version.release", release, MAX_BUFFER)) {
        if (get_android_property("ro.build.version.sdk", sdk, MAX_BUFFER)) {
            snprintf(version, MAX_BUFFER, "%s (API %s)", release, sdk);
        } else {
            strncpy(version, release, MAX_BUFFER - 1);
        }
    } else {
        strcpy(version, "Unknown");
    }

    /* Get device model */
    char manufacturer[MAX_BUFFER] = {0};
    char device_model[MAX_BUFFER] = {0};

    get_android_property("ro.product.manufacturer", manufacturer, MAX_BUFFER);

    if (!get_android_property("ro.product.marketname", device_model, MAX_BUFFER)) {
        get_android_property("ro.product.model", device_model, MAX_BUFFER);
    }

    if (manufacturer[0] && device_model[0]) {
        /* Check if model already contains manufacturer */
        char lower_model[MAX_BUFFER];
        char lower_manufacturer[MAX_BUFFER];

        strncpy(lower_model, device_model, MAX_BUFFER - 1);
        strncpy(lower_manufacturer, manufacturer, MAX_BUFFER - 1);

        for (char* p = lower_model; *p; p++) *p = tolower(*p);
        for (char* p = lower_manufacturer; *p; p++) *p = tolower(*p);

        if (strstr(lower_model, lower_manufacturer) == lower_model) {
            strncpy(model, device_model, MAX_BUFFER - 1);
        } else {
            snprintf(model, MAX_BUFFER, "%s %s", manufacturer, device_model);
        }
    } else if (device_model[0]) {
        strncpy(model, device_model, MAX_BUFFER - 1);
    } else if (manufacturer[0]) {
        strncpy(model, manufacturer, MAX_BUFFER - 1);
    } else {
        strcpy(model, "Unknown");
    }

    return 1;
}
#endif

#ifdef PLATFORM_MACOS
/* macOS-specific detection */
static int get_macos_info(char* name, char* version, char* model) {
    strcpy(name, "macOS");

    /* Get macOS version */
    char osversion[MAX_BUFFER];
    size_t size = sizeof(osversion);

    if (sysctlbyname("kern.osproductversion", osversion, &size, NULL, 0) == 0) {
        strncpy(version, osversion, MAX_BUFFER - 1);
    } else {
        struct utsname uts;
        if (uname(&uts) == 0) {
            strncpy(version, uts.release, MAX_BUFFER - 1);
        } else {
            strcpy(version, "Unknown");
        }
    }

    /* Get Mac model */
    char hw_model[MAX_BUFFER];
    size_t model_size = sizeof(hw_model);

    if (sysctlbyname("hw.model", hw_model, &model_size, NULL, 0) == 0) {
        strncpy(model, hw_model, MAX_BUFFER - 1);
    } else if (gethostname(model, MAX_BUFFER) != 0) {
        strcpy(model, "Unknown");
    }

    return 1;
}
#endif

/* Main get_device_info function */
static PyObject* native_get_device_info(PyObject* self, PyObject* args) {
    char platform_name[MAX_BUFFER];
    char os_name[MAX_BUFFER];
    char os_version[MAX_BUFFER];
    char device_model[MAX_BUFFER];

    /* Platform-specific detection using compile-time switches */
    #ifdef PLATFORM_WINDOWS
        strcpy(platform_name, "Windows");
        get_windows_info(os_name, os_version, device_model);
    #elif PLATFORM_ANDROID
        strcpy(platform_name, "Android");
        get_android_info(os_name, os_version, device_model);
    #elif PLATFORM_MACOS
        strcpy(platform_name, "macOS");
        get_macos_info(os_name, os_version, device_model);
    #elif PLATFORM_LINUX
        strcpy(platform_name, "Linux");
        get_linux_distro_info(os_name, os_version);
        get_linux_model(device_model);
    #else
        strcpy(platform_name, "Unknown");
        strcpy(os_name, "Unknown");
        strcpy(os_version, "Unknown");
        strcpy(device_model, "Unknown");
    #endif

    /* Detect runtime environments */
    int env_flags = detect_environments();

    /* Build result dictionary matching DeviceInfo structure */
    PyObject* result = PyDict_New();
    if (!result) return NULL;

    /* Add platform */
    PyObject* py_platform = PyUnicode_FromString(platform_name);
    PyDict_SetItemString(result, "platform", py_platform);
    Py_DECREF(py_platform);

    /* Add architecture */
    PyObject* py_arch = PyUnicode_FromString(ARCH_STRING);
    PyDict_SetItemString(result, "architecture", py_arch);
    Py_DECREF(py_arch);

    /* Add name */
    PyObject* py_name = PyUnicode_FromString(os_name);
    PyDict_SetItemString(result, "name", py_name);
    Py_DECREF(py_name);

    /* Add version */
    PyObject* py_version = PyUnicode_FromString(os_version);
    PyDict_SetItemString(result, "version", py_version);
    Py_DECREF(py_version);

    /* Add model */
    PyObject* py_model = PyUnicode_FromString(device_model);
    PyDict_SetItemString(result, "model", py_model);
    Py_DECREF(py_model);

    /* Add environments */
    PyObject* py_environments = environments_to_list(env_flags);
    if (!py_environments) {
        Py_DECREF(result);
        return NULL;
    }
    PyDict_SetItemString(result, "environments", py_environments);
    Py_DECREF(py_environments);

    return result;
}

/* Module method definitions */
static PyMethodDef DeviceNativeMethods[] = {
    {"get_device_info", native_get_device_info, METH_NOARGS,
     "Get device information using native APIs (returns dict)"},
    {NULL, NULL, 0, NULL}
};

/* Module definition */
static struct PyModuleDef devicenativemodule = {
    PyModuleDef_HEAD_INIT,
    "_device_native",
    "Native device detection module for high-performance platform detection",
    -1,
    DeviceNativeMethods
};

/* Module initialization */
PyMODINIT_FUNC PyInit__device_native(void) {
    return PyModule_Create(&devicenativemodule);
}
