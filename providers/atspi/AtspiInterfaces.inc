// AT-SPI protocol declarations from WebKit b95c91b1c0ee43cc86d25ff7af73038f67a88e04.
static constexpr const char interfaceXml[] = R"ATSPI(<node>
<interface name="org.a11y.atspi.Accessible">

  <property name="Name" type="s" access="read" />

  <property name="Description" type="s" access="read" />

  <property name="Parent" type="(so)" access="read">
    <annotation name="org.qtproject.QtDBus.QtTypeName" value="QSpiObjectReference" />
  </property>

  <property name="ChildCount" type="i" access="read" />

  <property name="Locale" type="s" access="read" />

  <property name="AccessibleId" type="s" access="read" />

  <method name="GetChildAtIndex">
    <arg direction="in" name="index" type="i" />
    <arg direction="out" type="(so)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiObjectReference" />
  </method>

  <method name="GetChildren">
    <arg direction="out" type="a(so)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiObjectReferenceArray" />
  </method>

  <method name="GetIndexInParent">
    <arg direction="out" type="i" />
  </method>

  <method name="GetRelationSet">
    <arg direction="out" type="a(ua(so))" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiRelationArray" />
  </method>

  <method name="GetRole">
    <arg direction="out" type="u" />
  </method>

  <method name="GetRoleName">
    <arg direction="out" type="s" />
  </method>

  <method name="GetLocalizedRoleName">
    <arg direction="out" type="s" />
  </method>

  <method name="GetState">
    <arg direction="out" type="au" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiIntList" />
  </method>

  <method name="GetAttributes">
    <arg direction="out" type="a{ss}" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiAttributeSet" />
  </method>

  <method name="GetApplication">
    <arg direction="out" type="(so)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiObjectReference" />
  </method>

  <method name="GetInterfaces">
    <arg direction="out" type="as" />
  </method>

</interface>

<interface name="org.a11y.atspi.Application">

  <property name="ToolkitName" type="s" access="read" />

  <property name="Version" type="s" access="read" />

  <property name="AtspiVersion" type="s" access="read" />
  <property name="Id" type="i" access="readwrite" />

  <method name="GetLocale">
    <arg direction="in" name="lctype" type="u" />
    <arg direction="out" type="s" />
  </method>

  <method name="RegisterEventListener">
    <arg direction="in" name="event" type="s" />
  </method>

  <method name="DeregisterEventListener">
    <arg direction="in" name="event" type="s" />
  </method>

</interface>

<interface name="org.a11y.atspi.Component">

  <method name="Contains">
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="in" name="coord_type" type="u" />
    <arg direction="out" type="b" />
  </method>

  <method name="GetAccessibleAtPoint">
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="in" name="coord_type" type="u" />
    <arg direction="out" type="(so)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiObjectReference" />
  </method>

  <method name="GetExtents">
    <arg direction="in" name="coord_type" type="u" />
    <arg direction="out" type="(iiii)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiRect" />
  </method>

  <method name="GetPosition">
    <arg direction="in" name="coord_type" type="u" />
    <arg direction="out" name="x" type="i" />
    <arg direction="out" name="y" type="i" />
  </method>

  <method name="GetSize">
    <arg direction="out" name="width" type="i" />
    <arg direction="out" name="height" type="i" />
  </method>

  <method name="GetLayer">
    <arg direction="out" type="u" />
  </method>

  <method name="GetMDIZOrder">
    <arg direction="out" type="n" />
  </method>

  <method name="GrabFocus">
    <arg direction="out" type="b" />
  </method>

  <method name="GetAlpha">
    <arg direction="out" type="d" />
  </method>

  <method name="SetExtents">
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="in" name="width" type="i" />
    <arg direction="in" name="height" type="i" />
    <arg direction="in" name="coord_type" type="u" />
    <arg direction="out" type="b" />
  </method>

  <method name="SetPosition">
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="in" name="coord_type" type="u" />
    <arg direction="out" type="b" />
  </method>

  <method name="SetSize">
    <arg direction="in" name="width" type="i" />
    <arg direction="in" name="height" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="ScrollTo">
    <arg direction="in" name="type" type="u" />
    <arg direction="out" type="b" />
  </method>

  <method name="ScrollToPoint">
    <arg direction="in" name="type" type="u" />
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="out" type="b" />
  </method>

</interface>

<interface name="org.a11y.atspi.Action">

  <property name="NActions" type="i" access="read" />

  <method name="GetDescription">
    <arg type="i" name="index" direction="in" />
    <arg type="s" direction="out" />
  </method>

  <method name="GetName">
    <arg type="i" name="index" direction="in" />
    <arg type="s" direction="out" />
  </method>

  <method name="GetLocalizedName">
    <arg type="i" name="index" direction="in" />
    <arg type="s" direction="out" />
  </method>

  <method name="GetKeyBinding">
    <arg type="i" name="index" direction="in" />
    <arg type="s" direction="out" />
  </method>

  <method name="GetActions">
    <arg direction="out" type="a(sss)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiActionArray" />
  </method>

  <method name="DoAction">
    <arg direction="in" name="index" type="i" />
    <arg direction="out" type="b" />
  </method>

</interface>

<interface name="org.a11y.atspi.Value">

        <property name="MinimumValue" type="d" access="read" />

        <property name="MaximumValue" type="d" access="read" />

        <property name="MinimumIncrement" type="d" access="read" />

        <property name="CurrentValue" type="d" access="readwrite" />

</interface>

<interface name="org.a11y.atspi.Text">

  <property name="CharacterCount" type="i" access="read" />

  <property name="CaretOffset" type="i" access="read" />

  <method name="GetStringAtOffset">
    <arg direction="in" name="offset" type="i" />
    <arg direction="in" name="granularity" type="u" />
    <arg direction="out" type="s" />
    <arg direction="out" name="startOffset" type="i" />
    <arg direction="out" name="endOffset" type="i" />
  </method>

  <method name="GetText">
    <arg direction="in" name="startOffset" type="i" />
    <arg direction="in" name="endOffset" type="i" />
    <arg direction="out" type="s" />
  </method>

  <method name="SetCaretOffset">
    <arg direction="in" name="offset" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="GetTextBeforeOffset">
    <arg direction="in" name="offset" type="i" />
    <arg direction="in" name="type" type="u" />
    <arg direction="out" type="s" />
    <arg direction="out" name="startOffset" type="i" />
    <arg direction="out" name="endOffset" type="i" />
  </method>

  <method name="GetTextAtOffset">
    <arg direction="in" name="offset" type="i" />
    <arg direction="in" name="type" type="u" />
    <arg direction="out" type="s" />
    <arg direction="out" name="startOffset" type="i" />
    <arg direction="out" name="endOffset" type="i" />
  </method>

  <method name="GetTextAfterOffset">
    <arg direction="in" name="offset" type="i" />
    <arg direction="in" name="type" type="u" />
    <arg direction="out" type="s" />
    <arg direction="out" name="startOffset" type="i" />
    <arg direction="out" name="endOffset" type="i" />
  </method>

  <method name="GetCharacterAtOffset">
    <arg name="offset" type="i" direction="in" />
    <arg type="i" direction="out" />
  </method>

  <method name="GetAttributeValue">
    <arg direction="in" name="offset" type="i" />
    <arg direction="in" name="attributeName" type="s" />
    <arg direction="out" type="s" />
  </method>

  <method name="GetAttributes">
    <arg direction="in" name="offset" type="i" />
    <arg direction="out" type="a{ss}" />
    <arg direction="out" name="startOffset" type="i" />
    <arg direction="out" name="endOffset" type="i" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiAttributeSet" />
  </method>

  <method name="GetDefaultAttributes">
    <arg direction="out" type="a{ss}" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiAttributeSet" />
  </method>

  <method name="GetCharacterExtents">
    <arg direction="in" name="offset" type="i" />
    <arg direction="out" name="x" type="i" />
    <arg direction="out" name="y" type="i" />
    <arg direction="out" name="width" type="i" />
    <arg direction="out" name="height" type="i" />
    <arg direction="in" name="coordType" type="u" />
  </method>

  <method name="GetOffsetAtPoint">
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="in" name="coordType" type="u" />
    <arg direction="out" type="i" />
  </method>

  <method name="GetNSelections">
    <arg direction="out" type="i" />
  </method>

  <method name="GetSelection">
    <arg direction="in" name="selectionNum" type="i" />
    <arg direction="out" name="startOffset" type="i" />
    <arg direction="out" name="endOffset" type="i" />
  </method>

  <method name="AddSelection">
    <arg direction="in" name="startOffset" type="i" />
    <arg direction="in" name="endOffset" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="RemoveSelection">
    <arg direction="in" name="selectionNum" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="SetSelection">
    <arg direction="in" name="selectionNum" type="i" />
    <arg direction="in" name="startOffset" type="i" />
    <arg direction="in" name="endOffset" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="GetRangeExtents">
    <arg direction="in" name="startOffset" type="i" />
    <arg direction="in" name="endOffset" type="i" />
    <arg direction="out" name="x" type="i" />
    <arg direction="out" name="y" type="i" />
    <arg direction="out" name="width" type="i" />
    <arg direction="out" name="height" type="i" />
    <arg direction="in" name="coordType" type="u" />
  </method>

  <method name="GetBoundedRanges">
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="in" name="width" type="i" />
    <arg direction="in" name="height" type="i" />
    <arg direction="in" name="coordType" type="u" />
    <arg direction="in" name="xClipType" type="u" />
    <arg direction="in" name="yClipType" type="u" />
    <arg direction="out" type="a(iisv)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiRangeList" />
  </method>

  <method name="GetAttributeRun">
    <arg direction="in" name="offset" type="i" />
    <arg direction="in" name="includeDefaults" type="b" />
    <arg direction="out" type="a{ss}" />
    <arg direction="out" name="startOffset" type="i" />
    <arg direction="out" name="endOffset" type="i" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiAttributeSet" />
  </method>

  <method name="GetDefaultAttributeSet">
    <arg direction="out" type="a{ss}" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiAttributeSet" />
  </method>

  <method name="ScrollSubstringTo">
    <arg direction="in" name="startOffset" type="i" />
    <arg direction="in" name="endOffset" type="i" />
    <arg direction="in" name="type" type="u" />
    <arg direction="out" type="b" />
  </method>

  <method name="ScrollSubstringToPoint">
    <arg direction="in" name="startOffset" type="i" />
    <arg direction="in" name="endOffset" type="i" />
    <arg direction="in" name="type" type="u" />
    <arg direction="in" name="x" type="i" />
    <arg direction="in" name="y" type="i" />
    <arg direction="out" type="b" />
  </method>

</interface>

<interface name="org.a11y.atspi.EditableText">

  <method name="SetTextContents">
    <arg direction="in" name="newContents" type="s" />
    <arg direction="out" type="b" />
  </method>

  <method name="InsertText">
    <arg direction="in" name="position" type="i" />
    <arg direction="in" name="text" type="s" />
    <arg direction="in" name="length" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="CopyText">
    <arg direction="in" name="startPos" type="i" />
    <arg direction="in" name="endPos" type="i" />
  </method>

  <method name="CutText">
    <arg direction="in" name="startPos" type="i" />
    <arg direction="in" name="endPos" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="DeleteText">
    <arg direction="in" name="startPos" type="i" />
    <arg direction="in" name="endPos" type="i" />
    <arg direction="out" type="b" />
  </method>

  <method name="PasteText">
    <arg direction="in" name="position" type="i" />
    <arg direction="out" type="b" />
  </method>

</interface>

<interface name="org.a11y.atspi.Cache">

  <method name="GetItems">
    <arg direction="out" name="nodes" type="a((so)(so)(so)iiassusau)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.Out0" value="QSpiAccessibleCacheArray" />
  </method>

  <signal name="AddAccessible">
    <arg direction="out" name="nodeAdded" type="((so)(so)(so)iiassusau)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.In0" value="QSpiAccessibleCacheItem" />
  </signal>

  <signal name="RemoveAccessible">
    <arg direction="out" name="nodeRemoved" type="(so)" />
    <annotation name="org.qtproject.QtDBus.QtTypeName.In0" value="QSpiObjectReference" />
  </signal>

</interface>

</node>)ATSPI";
