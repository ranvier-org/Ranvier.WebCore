/// <summary>Typed facade calls exercised against actual browser DOM objects.</summary>
module NamedLookupBrowser

/// <summary>Returns the live document stylesheet list with its document association preserved.</summary>
let sheets (document: Ranvier.Dom.Document) = document.styleSheets

/// <summary>Returns the sheet selected by document ID, or null when the native lookup has no match.</summary>
let sheet (sheets: Ranvier.Dom.StyleSheetList) (name: string) = sheets.namedItem name

/// <summary>Returns the dataset value, with an empty string for a missing key.</summary>
let value (map: Ranvier.Dom.DOMStringMap) (name: string) = map.namedItem name

/// <summary>Assigns a dataset key through the generated setter.</summary>
let assign (map: Ranvier.Dom.DOMStringMap) (name: string) (text: string) = map.setNamedItem (name, text)

/// <summary>Removes a dataset key through the generated deleter.</summary>
let remove (map: Ranvier.Dom.DOMStringMap) (name: string) = map.deleteNamedProperty name
