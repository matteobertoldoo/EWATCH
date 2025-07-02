[app]

title = Medical Registration
package.name = medicalreg
package.domain = org.medical
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy,android,pyjnius,requests

orientation = portrait
fullscreen = 0

android.permissions = CAMERA, WRITE_EXTERNAL_STORAGE, INTERNET
android.api = 35
android.minapi = 23
#android.ndk = 27c
android.accept_sdk_license = True

p4a.branch = develop


[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2