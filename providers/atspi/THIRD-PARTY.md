# Optional provider source and dependency notices

This inventory distinguishes embedded source material, build headers and separately installed shared libraries.
It records identified terms without assigning a license to the Ranvier provider.

## Embedded protocol declarations

`AtspiInterfaces.inc` is compiled into the provider. `generate-interfaces.py` derives it from WebKit commit
`b95c91b1c0ee43cc86d25ff7af73038f67a88e04`, directory `Source/WebCore/accessibility/atspi/xml/`, files
`Accessible.xml`, `Application.xml`, `Component.xml`, `Action.xml`, `Value.xml`, `Text.xml`, `EditableText.xml`
and `Cache.xml`. The generator retains interface elements and changes signal argument directions to `out` for GDBus.
The source files at that pin contain no per-file copyright or license notice. This inventory preserves their exact
origin without assigning BSD or LGPL terms to those XML files. Absence of a notice does not establish a license.

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

C/C++ standard-library headers and compiler runtime libraries are toolchain inputs. Producer evidence records
the actual compiler/runtime identity and dynamic dependency list. This inventory does not infer their complete
license closure from the absence of extra files in the package.

## Original project license metadata

No original-project LICENSE file or SPDX declaration was identified in the provider source. The existing Native,
managed and aggregate project files use `PackageLicenseFile=NOTICE.md`; their shared NOTICE is a component inventory.
This optional packager follows that convention with NuGet `license` type `file` pointing to its truthful `NOTICE.md`,
and carries this inventory alongside it. This names the shipped notice without inventing a license grant or SPDX expression.
That is a metadata limitation, not an additional approval or packaging gate. It does not change final cohort/version
allocation requirements. No project license is inferred from system-library terms or WebKit's licensing page.

The included LGPL-2.1 text describes its own redistribution/linking conditions, including notice/license text and
applicable source/relinking provisions in sections 5 and 6. Its inclusion identifies the cited dependency terms;
it does not establish that every provision applies to every unbundled component or that a complete application
distribution has been audited. Bundling additional system or compiler runtime binaries changes that distribution's
component closure and corresponding notices.
