# Optional provider source and dependency notices

This inventory distinguishes embedded source material, build headers and separately installed shared libraries.
It does not assign a license to the Ranvier provider or approve public distribution.

## Embedded protocol declarations

`AtspiInterfaces.inc` is compiled into the provider. `generate-interfaces.py` derives it from WebKit commit
`b95c91b1c0ee43cc86d25ff7af73038f67a88e04`, directory `Source/WebCore/accessibility/atspi/xml/`, files
`Accessible.xml`, `Application.xml`, `Component.xml`, `Action.xml`, `Value.xml`, `Text.xml`, `EditableText.xml`
and `Cache.xml`. The generator retains interface elements and changes signal argument directions to `out` for GDBus.
The source files at that pin contain no per-file copyright or license notice. Their applicable terms and attribution
must be resolved before public release; absence of a notice does not establish a permissive license.

Source: [pinned Accessible.xml](https://github.com/WebKit/WebKit/blob/b95c91b1c0ee43cc86d25ff7af73038f67a88e04/Source/WebCore/accessibility/atspi/xml/Accessible.xml).
[WebKit licensing guidance](https://docs.webkit.org/Other/Licensing.html) describes mixed BSD and LGPL source and
requires preserving the original notices when moving existing code. Its general guidance does not identify the
license of these unmarked XML files.

## System libraries and build headers

The module dynamically links system GIO, GObject and GLib. Their binaries are not packaged here. The reviewed
GLib 2.80.0 `gio/gdbusconnection.h` identifies LGPL-2.1-or-later, copyright 2008–2010 Red Hat, Inc.; other GLib files
retain their respective owners. Sources: [header](https://github.com/GNOME/glib/blob/2.80.0/gio/gdbusconnection.h),
[license text](https://github.com/GNOME/glib/blob/2.80.0/LICENSES/LGPL-2.1-or-later.txt).

The build includes AT-SPI headers for enum constants. It does not link libatspi; libatspi and its independent clients
are qualification inputs. The reviewed at-spi2-core 2.52.0 `atspi/atspi-constants.h` states LGPL-2.1-or-later and
copyright 2010, 2011 Novell, Inc. and 2012 SUSE LINUX Products GmbH, Nuernberg, Germany.
Sources: [header](https://github.com/GNOME/at-spi2-core/blob/AT_SPI2_CORE_2_52_0/atspi/atspi-constants.h),
[license text](https://github.com/GNOME/at-spi2-core/blob/AT_SPI2_CORE_2_52_0/COPYING).
The package carries a verbatim LGPL-2.1 text in `licenses/LGPL-2.1.txt` for these notices. That file does not license
the whole provider. Separately supplied shared libraries retain their own licenses and distribution obligations.

C/C++ standard-library headers and compiler runtime libraries are toolchain inputs. A final producer must retain
its actual compiler/runtime identity and dynamic dependency list. This inventory does not infer their complete
license closure from the absence of extra files in the package.

## Public release requirements

The repository and provider currently carry no project LICENSE file. The rights holder must specify the provider
and public ABI header terms and supply the corresponding text. Resolve the embedded XML attribution/terms and
review the actual final binary's dependency and header-derived content closure. Only then set accurate NuGet
`license` metadata, ship the required notices/texts and arrange any applicable source/relinking materials.
Keep the public identity/version gate closed until that review is recorded. No project license is inferred from
the system libraries' licenses or WebKit's general licensing page.
