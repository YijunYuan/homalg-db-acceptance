import Lean

open Lean

namespace HomAlgExport

/-- Export parameters: imports and output filtering are deliberately independent. -/
structure Config where
  roots : Array Name := #[]
  prefixName : Name := `HomAlg
  out : Option System.FilePath := none
  checkConstants : Array Name := #[]

/-- A module's constant owner, including constants outside the selected prefix. -/
def moduleOf (env : Environment) (name : Name) : Option Name :=
  env.getModuleIdxFor? name |>.map (env.header.moduleNames[·]!)

/-- Only flat document node modules have a node id; root modules do not. -/
def nodeId (name : Name) : Option String :=
  match name.toString.splitOn "." with
  | ["HomAlg", doc, localId] => some s!"{doc}.{localId}"
  | _ => none

/-- True for every project constant, regardless of the requested output prefix. -/
def isProject (env : Environment) (name : Name) : Bool :=
  (moduleOf env name).any ((`HomAlg).isPrefixOf ·)

/-- Sort names lexically so JSON and closure hashes do not depend on hash-set order. -/
def sortedNames (names : NameSet) : List Name :=
  names.toList.mergeSort (fun a b => a.toString <= b.toString)

/-- Fixed-width lower-case rendering of Lean's 64-bit structural hashes. -/
def hex64 (value : UInt64) : String := Id.run do
  let digits := "0123456789abcdef".toList.toArray
  let mut result := ""
  let mut value := value.toNat
  for _ in [:16] do
    result := String.singleton digits[value % 16]! ++ result
    value := value / 16
  return result

/-- Internal helper names are filtered narrowly; names such as eq_degree_zero survive. -/
def isAuxiliary (name : Name) : Bool :=
  let numbered (s pre : String) :=
    s.startsWith pre && !(s.drop pre.length).isEmpty && (s.drop pre.length).all Char.isDigit
  name.isInternal || match name with
    | .str _ s => s.startsWith "_" || numbered s "proof_" || numbered s "match_" ||
        numbered s "eq_" || numbered s "_sizeOf_" ||
        ["eq_def", "eq_unfold", "rec", "recOn", "casesOn", "brecOn", "binductionOn",
         "noConfusion", "noConfusionType", "below", "ibelow"].contains s
    | _ => false

/-- Dependency traversal expands every same-module constant, including named helpers. -/
structure Uses where
  directSorry : Bool := false
  project : NameSet := {}
  external : NameSet := {}

/-- Finite graph traversal has no silent fuel limit. Other modules form its boundary. -/
partial def collectUses (env : Environment) (owner : Name) (todo : List Name)
    (seen : NameSet := {}) (acc : Uses := {}) : Uses :=
  match todo with
  | [] => acc
  | name :: rest =>
    if seen.contains name then collectUses env owner rest seen acc else
    let seen := seen.insert name
    if name == ``sorryAx then
      collectUses env owner rest seen { acc with directSorry := true, external := acc.external.insert name }
    else if isProject env name && moduleOf env name == some owner then
      match env.find? name with
      | none => collectUses env owner rest seen acc
      | some info =>
        let more := info.type.getUsedConstants ++
          ((info.value? (allowOpaque := true)).map (·.getUsedConstants) |>.getD #[])
        collectUses env owner (more.toList ++ rest) seen acc
    else if isProject env name then
      collectUses env owner rest seen { acc with project := acc.project.insert name }
    else
      collectUses env owner rest seen { acc with external := acc.external.insert name }

/-- Collect the semantic boundary below a type; theorem proof bodies are irrelevant. -/
partial def meaningClosure (env : Environment) (todo : List Name) (seen : NameSet := {}) : NameSet :=
  match todo with
  | [] => seen
  | name :: rest =>
    if seen.contains name || !isProject env name then meaningClosure env rest seen else
    let seen := seen.insert name
    match env.find? name with
    | none => meaningClosure env rest seen
    | some info => Id.run do
      let mut more := info.type.getUsedConstants
      match info with
      | .defnInfo value => more := more ++ value.value.getUsedConstants
      | .inductInfo value =>
        for ctor in value.ctors do
          if let some ctorInfo := env.find? ctor then
            more := (more.push ctor) ++ ctorInfo.type.getUsedConstants
      | _ => pure ()
      return meaningClosure env (more.toList ++ rest) seen

/-- Hash reachable project meanings, including definitions hidden behind unchanged type names. -/
def meaningHash (env : Environment) (type : Expr) : UInt64 := Id.run do
  let mut result := type.hash
  for name in sortedNames (meaningClosure env type.getUsedConstants.toList) do
    if let some info := env.find? name then
      let valueHash := match info with
        | .defnInfo value => value.value.hash
        | _ => 0
      result := mixHash result (mixHash (hash name) (mixHash info.type.hash valueHash))
  return result

/-- Determine whether a value hides data-valued sorry, following same-module data helpers. -/
partial def isHollow (env : Environment) (owner : Name) (todo : List Name)
    (seen : NameSet := {}) : MetaM Bool := do
  match todo with
  | [] => return false
  | name :: rest =>
    if seen.contains name then return ← isHollow env owner rest seen
    let seen := seen.insert name
    let some info := env.find? name | return ← isHollow env owner rest seen
    if (← Meta.isProp info.type) then return ← isHollow env owner rest seen
    let some value := info.value? (allowOpaque := true)
      | return ← isHollow env owner rest seen
    let hollow ← IO.mkRef false
    discard <| Meta.transform value (pre := fun expression => do
      if expression.isAppOf ``sorryAx then
        unless (← Meta.isProp (← Meta.inferType expression)) do hollow.set true
        -- Do not inspect partial applications of a labelled sorry as if they were data.
        return .done expression
      return .continue)
    if ← hollow.get then return true
    let more := value.getUsedConstants.toList.filter (moduleOf env · == some owner)
    return ← isHollow env owner (more ++ rest) seen

/-- Detect structures or classes whose proposition field is precisely the requested conclusion. -/
def packagedFields (env : Environment) (prefixName : Name) (type : Expr) : MetaM (Array Json) :=
  Meta.forallTelescope type fun args conclusion => do
    let mut result := #[]
    let closedConclusion ← Meta.mkLambdaFVars args conclusion
    for index in [:args.size] do
      let arg := args[index]!
      let argType ← instantiateMVars (← Meta.inferType arg)
      let .const structName _ := argType.headBeta.getAppFn | continue
      unless (moduleOf env structName).any (prefixName.isPrefixOf ·) do continue
      unless isStructure env structName do continue
      let fields := (getStructureFieldsFlattened env structName).toList.eraseDups
      for field in fields do
        let projection ← Meta.mkProjection arg field
        let fieldType := (← instantiateMVars (← Meta.inferType projection)).headBeta
        unless ← Meta.isProp fieldType do continue
        if (← Meta.mkLambdaFVars args fieldType).eqv closedConclusion then
          result := result.push <| Json.mkObj [
            ("binder", toJson index), ("structure", toJson structName.toString),
            ("field", toJson projection.getAppFn.constName!.toString)]
    return result

/-- Fold referenced project constants to unique node ids, excluding root modules. -/
def usedNodes (env : Environment) (names : NameSet) : Array String :=
  let values := (sortedNames names).filterMap fun name => moduleOf env name |>.bind nodeId
  (values.toArray.qsort (· < ·)).toList.eraseDups.toArray

/-- A structure's signature includes its constructor types, not just its sort. -/
def interfaceConstants (env : Environment) (info : ConstantInfo) : Array Name := Id.run do
  let mut names := info.type.getUsedConstants
  if let .inductInfo value := info then
    for ctor in value.ctors do
      if let some ctorInfo := env.find? ctor then
        names := names ++ ctorInfo.type.getUsedConstants
  return names

/-- Capture Lean's builtin printers before loading user modules. Imported notation,
delaborators, formatters and name-shortening must not alter persistent type text. -/
def canonicalPrinter : IO (Environment → Environment) := do
  let delab ← PrettyPrinter.Delaborator.delabAttribute.tableRef.get
  let unexpand ← PrettyPrinter.Delaborator.appUnexpanderAttribute.tableRef.get
  let formatter ← PrettyPrinter.formatterAttribute.tableRef.get
  let parenthesizer ← PrettyPrinter.parenthesizerAttribute.tableRef.get
  let category ← PrettyPrinter.categoryParenthesizerAttribute.tableRef.get
  return fun env =>
    let env := PrettyPrinter.Delaborator.delabAttribute.ext.modifyState env
      (fun _ => KeyedDeclsAttribute.mkStateOfTable delab)
    let env := PrettyPrinter.Delaborator.appUnexpanderAttribute.ext.modifyState env
      (fun _ => KeyedDeclsAttribute.mkStateOfTable unexpand)
    let env := PrettyPrinter.formatterAttribute.ext.modifyState env
      (fun _ => KeyedDeclsAttribute.mkStateOfTable formatter)
    let env := PrettyPrinter.parenthesizerAttribute.ext.modifyState env
      (fun _ => KeyedDeclsAttribute.mkStateOfTable parenthesizer)
    PrettyPrinter.categoryParenthesizerAttribute.ext.modifyState env
      (fun _ => KeyedDeclsAttribute.mkStateOfTable category)

/-- Print fully qualified types with fixed builtin syntax, omitting implicit
arguments and proof terms while kernel expression hashes retain their content. -/
def canonicalType (printEnv : Environment) (type : Expr) : MetaM String :=
  withEnv printEnv <| withOptions (fun _ =>
    let options : Options := {}
    let options := options.set `format.width (100 : Nat)
    let options := options.setBool `pp.notation false
    let options := options.setBool `pp.fullNames true
    let options := options.setBool `pp.fieldNotation false
    let options := options.setBool `pp.explicit false
    let options := options.setBool `pp.coercions false
    let options := options.setBool `pp.universes true
    let options := options.setBool `pp.proofs false
    let options := options.set `pp.proofs.threshold (0 : Nat)
    let options := options.setBool `pp.deepTerms true
    let options := options.setBool `pp.analyze false
    let options := options.setBool `pp.beta false
    let options := options.set `pp.maxSteps (2 ^ 64 : Nat)
    options.setBool `pp.unicode.fun true) do
    return (← PrettyPrinter.ppExpr type).pretty 100 |>.trimAscii.toString

/-- Export one user-visible declaration and its authoritative compiled properties. -/
def declaration (env printEnv : Environment) (prefixName owner name : Name) (info : ConstantInfo)
    (line : Nat) : MetaM Json := do
  let typeUses := collectUses env owner (interfaceConstants env info).toList
  let valueUses := collectUses env owner
    (((info.value? (allowOpaque := true)).map (·.getUsedConstants) |>.getD #[]).toList)
  let axioms ← collectAxioms name
  let reducibility ← getReducibilityStatus name
  let kind ← match info with
    | .thmInfo _ => pure "theorem"
    | .defnInfo _ =>
      if (env.getProjectionFnInfo? name).isSome then pure "projection"
      else if reducibility == .instanceReducible || (← Meta.isInstance name) then pure "instance"
      else if reducibility == .reducible then pure "abbrev" else pure "def"
    | .inductInfo _ => pure <| if isClass env name then "class"
        else if isStructure env name then "structure" else "inductive"
    | .ctorInfo _ => pure "ctor"
    | .axiomInfo _ => pure "axiom"
    | .opaqueInfo _ => pure "opaque"
    | _ => pure "other"
  let isProp ← Meta.isProp info.type
  let typeString ← canonicalType printEnv info.type
  let typeExternal := (sortedNames typeUses.external).map Name.toString
  let valueExternal := (sortedNames valueUses.external).map Name.toString
  let typeNodes := usedNodes env typeUses.project
  let valueNodes := (usedNodes env valueUses.project).filter (!typeNodes.contains ·)
  let mut fields := [
    ("name", toJson name.toString), ("kind", toJson kind), ("type", toJson typeString),
    ("type_hash", toJson (hex64 info.type.hash)),
    ("meaning_hash", toJson (hex64 (meaningHash env info.type))),
    ("is_prop", toJson isProp), ("hollow", toJson (← isHollow env owner [name])),
    ("docstring", toJson ((← findDocString? env name).getD "")), ("line", toJson line),
    ("axioms", toJson ((axioms.toList.map Name.toString).mergeSort (· <= ·))),
    ("direct_sorry", toJson (typeUses.directSorry || valueUses.directSorry)),
    ("transitive_sorry", toJson (axioms.contains ``sorryAx)),
    ("type_uses_nodes", toJson typeNodes), ("value_uses_nodes", toJson valueNodes),
    ("type_uses_external", toJson (typeExternal.take 200)),
    ("value_uses_external", toJson (valueExternal.take 200)),
    ("type_uses_external_truncated", toJson (decide (typeExternal.length > 200))),
    ("value_uses_external_truncated", toJson (decide (valueExternal.length > 200)))]
  if kind == "instance" then
    let ownDoc := owner.getPrefix
    let usesOwnDoc ← Meta.forallTelescope info.type fun _ conclusion =>
      pure <| conclusion.getUsedConstants.any fun constant =>
        (moduleOf env constant).any (ownDoc.isPrefixOf ·)
    fields := fields ++ [("is_global_instance", toJson (← Meta.isInstance name)),
      ("instance_type_uses_own_doc", toJson usesOwnDoc)]
  if isProp then fields := fields ++ [("packaged_fields", toJson (← packagedFields env prefixName info.type))]
  return Json.mkObj fields

/-- Build every selected module's JSON in one CoreM invocation with loaded extensions. -/
def exportModules (env printEnv : Environment) (prefixName : Name) : CoreM (Array Json) := do
  let mut result := #[]
  let names := env.header.moduleNames
  for index in [:names.size] do
    let owner := names[index]!
    unless prefixName.isPrefixOf owner do continue
    let mut decls := #[]
    let constants := env.header.moduleData[index]!.constNames.qsort
      (fun a b => a.toString < b.toString)
    for name in constants do
      if isAuxiliary name then continue
      let some ranges ← findDeclarationRanges? name | continue
      let some info := env.find? name | continue
      decls := decls.push (← (declaration env printEnv prefixName owner name info ranges.range.pos.line).run')
    result := result.push <| Json.mkObj [
      ("module", toJson owner.toString), ("node_id", toJson (nodeId owner)), ("decls", toJson decls)]
  return result.qsort fun a b =>
    (a.getObjValAs? String "module" |>.toOption.getD "") <
      (b.getObjValAs? String "module" |>.toOption.getD "")

/-- Reject unknown options rather than silently ignoring a misspelled scope selector. -/
partial def parseArgs (args : List String) (config : Config := {}) : IO Config := do
  match args with
  | [] => return config
  | "--root" :: value :: rest => parseArgs rest { config with roots := config.roots.push value.toName }
  | "--prefix" :: value :: rest => parseArgs rest { config with prefixName := value.toName }
  | "--out" :: value :: rest => parseArgs rest { config with out := some value }
  | "--check-constants" :: file :: rest =>
    let text ← IO.FS.readFile file
    let names := text.splitOn "\n" |>.map (·.trimAscii.toString) |>.filter (!·.isEmpty)
    parseArgs rest { config with checkConstants := names.toArray.map String.toName }
  | "--modules" :: file :: rest =>
    let text ← IO.FS.readFile file
    let modules := text.splitOn "\n" |>.map (·.trimAscii.toString) |>.filter (!·.isEmpty)
    parseArgs rest { config with roots := config.roots ++ modules.toArray.map String.toName }
  | option :: _ => throw <| IO.userError s!"Unknown or incomplete exporter option: {option}"

/-- Discover source node modules when no explicit import list was given. -/
def discoverModules : IO (Array Name) := do
  let mut result := #[]
  for entry in ← System.FilePath.readDir "HomAlg" do
    unless ← entry.path.isDir do continue
    for file in ← entry.path.readDir do
      if file.path.extension == some "lean" then
        if let some stem := file.path.fileStem then
          result := result.push s!"HomAlg.{entry.fileName}.{stem}".toName
  return result.qsort (fun a b => a.toString < b.toString)

/-- Canonical two-space JSON, matching Python sort_keys/indent/ensure_ascii=False. -/
partial def canonicalJson (value : Json) (depth : Nat := 0) : String :=
  let indent := String.ofList (List.replicate (2 * depth) ' ')
  let childIndent := indent ++ "  "
  match value with
  | .arr values =>
    if values.isEmpty then "[]" else
    "[\n" ++ String.intercalate ",\n"
      (values.toList.map fun child => childIndent ++ canonicalJson child (depth + 1)) ++
      "\n" ++ indent ++ "]"
  | .obj values =>
    let fields := values.foldl (fun acc key child => (key, child) :: acc) []
      |>.mergeSort (fun a b => a.1 <= b.1)
    if fields.isEmpty then "{}" else
    "{\n" ++ String.intercalate ",\n" (fields.map fun (key, child) =>
      childIndent ++ (Json.str key).compress ++ ": " ++ canonicalJson child (depth + 1)) ++
      "\n" ++ indent ++ "}"
  | _ => value.compress

/-- Preserve the exact release identifier used by the Lake dependency lock. -/
def mathlibRevision : IO String := do
  let text ← IO.FS.readFile "lake-manifest.json"
  let json ← IO.ofExcept (Json.parse text)
  let packages ← IO.ofExcept (json.getObjValAs? (Array Json) "packages")
  for package in packages do
    if (package.getObjValAs? String "name").toOption == some "mathlib" then
      return (package.getObjValAs? String "inputRev").toOption.getD
        ((package.getObjValAs? String "rev").toOption.getD "unknown")
  throw <| IO.userError "The Lake manifest has no pinned Mathlib dependency"

end HomAlgExport

/-- Load compiled modules with extensions, export their declarations, and emit one JSON value. -/
unsafe def main (args : List String) : IO UInt32 := do
  try
    if args.contains "--help" then
      IO.println "homalg-export [--modules FILE] [--root MODULE]... [--prefix MODULE] [--check-constants FILE] [--out FILE]"
      return 0
    let config ← HomAlgExport.parseArgs args
    let roots ← if config.roots.isEmpty then HomAlgExport.discoverModules else pure config.roots
    initSearchPath (← findSysroot)
    enableInitializersExecution
    let canonicalPrinter ← HomAlgExport.canonicalPrinter
    let env ← importModules (roots.map fun name => { module := name }) {}
      (trustLevel := 1024) (loadExts := true)
    let context : Core.Context := { fileName := "<export>", fileMap := default, maxHeartbeats := 0 }
    let (modules, _) ←
      (HomAlgExport.exportModules env (canonicalPrinter env) config.prefixName).toIO context { env }
    let result := Json.mkObj [
      ("generator", Json.mkObj [("name", toJson "homalg-export"), ("version", toJson "3")]),
      ("toolchain", toJson ((← IO.FS.readFile "lean-toolchain").trimAscii.toString)),
      ("mathlib_rev", toJson (← HomAlgExport.mathlibRevision)), ("modules", toJson modules),
      ("external_constants", Json.mkObj (config.checkConstants.toList.map fun name =>
        (name.toString, Json.mkObj [("exists", toJson ((env.find? name).isSome)),
          ("module", toJson ((HomAlgExport.moduleOf env name).map Name.toString))])))]
    let text := HomAlgExport.canonicalJson result ++ "\n"
    if let some file := config.out then
      if let some parent := file.parent then IO.FS.createDirAll parent
      let temporary := file.addExtension s!"tmp-{← IO.Process.getPID}"
      IO.FS.writeFile temporary text
      IO.FS.rename temporary file
    else IO.print text
    return 0
  catch error =>
    IO.eprintln s!"homalg-export: {error}"
    return 1
