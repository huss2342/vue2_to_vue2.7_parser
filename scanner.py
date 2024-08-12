import re
import esprima
from Vue2Component import Vue2Component

class Vue2Scanner:
    def __init__(self, content):
        self.content = content
        self.component = Vue2Component()

    def scan(self):
        script_content = self._extract_script_content()
        if not script_content:
            print("DEBUG: No script content found")
            return self.component

        try:
            parsed = esprima.parseModule(script_content)
            self._scan_imports(parsed)
            self._scan_export_default(parsed)
        except Exception as e:
            print(f"Error parsing script content: {str(e)}")

        return self.component

    def _extract_script_content(self):
        script_match = re.search(r'<script>([\s\S]*?)<\/script>', self.content)
        if script_match:
            script_content = script_match.group(1)
            print(f"DEBUG: Extracted script content:\n{script_content}")
            return script_content
        else:
            print("DEBUG: No script content found")
            return ""

    def _scan_export_default(self, parsed):
        for node in parsed.body:
            if node.type == 'ExportDefaultDeclaration':
                if node.declaration.type == 'ObjectExpression':
                    self._scan_component_object(node.declaration)

    def _scan_component_object(self, obj):
        for prop in obj.properties:
            if prop.key.name == 'name':
                self._scan_name(prop.value)
            elif prop.key.name == 'data':
                self._scan_data(prop.value)
            elif prop.key.name == 'components':
                self._scan_components(prop.value)
            elif prop.key.name == 'props':
                self._scan_props(prop.value)
            elif prop.key.name == 'computed':
                self._scan_computed(prop.value)
            elif prop.key.name == 'methods':
                self._scan_methods(prop.value)
            elif prop.key.name == 'watch':
                self._scan_watch(prop.value)
            elif prop.key.name in ['created', 'mounted', 'beforeDestroy']:
                self._scan_lifecycle_hook(prop.key.name, prop.value)

    def _scan_data(self, node):
        if node.type == 'FunctionExpression':
            # Extract the return statement from the function body
            return_statement = next((stmt for stmt in node.body.body if stmt.type == 'ReturnStatement'), None)

            if return_statement and return_statement.argument.type == 'ObjectExpression':
                # Process each property in the returned object
                for prop in return_statement.argument.properties:
                    if prop.type == 'Property':
                        key = prop.key.name
                        value = self._node_to_string(prop.value)
                        self.component.data[key] = value

        print(f"DEBUG: Scanned data: {self.component.data}")

    def _scan_watch(self, node):
        if node.type == 'ObjectExpression':
            for prop in node.properties:
                name = prop.key.name
                body = self._node_to_string(prop.value)
                self.component.watch[name] = body
        print(f"DEBUG: Scanned watch: {self.component.watch}")

    def _scan_lifecycle_hook(self, hook_name, node):
        body = self._node_to_string(node)
        self.component.lifecycle_hooks[hook_name] = body
        print(f"DEBUG: Scanned lifecycle hook {hook_name}: {body}")

    def _scan_name(self, node):
        if node.type == 'Literal':
            self.component.name = node.value
        print(f"DEBUG: Scanned name: {self.component.name}")

    def _scan_components(self, node):
        if node.type == 'ObjectExpression':
            for prop in node.properties:
                self.component.components[prop.key.name] = prop.key.name
        print(f"DEBUG: Scanned components: {self.component.components}")

    def _scan_props(self, node):
        if node.type == 'ObjectExpression':
            for prop in node.properties:
                prop_name = prop.key.name
                prop_value = self._get_prop_value(prop.value)
                self.component.props[prop_name] = prop_value
        print(f"DEBUG: Scanned props: {self.component.props}")

    def _get_prop_value(self, node):
        if node.type == 'Identifier':
            print(f"DEBUG: Found identifier: {node.name}")
            return node.name
        elif node.type == 'ObjectExpression':
            return {p.key.name: self._get_prop_value(p.value) for p in node.properties}
        elif node.type == 'Literal':
            return node.value
        return str(node)

    def _scan_methods(self, node):
        if node.type == 'ObjectExpression':
            for prop in node.properties:
                name = prop.key.name
                body = self._node_to_string(prop.value)
                self.component.methods[name] = body
        self.component.has_setup_content = bool(self.component.methods)
        print(f"DEBUG: Scanned methods: {self.component.methods}")

    def _scan_computed(self, properties):
        for prop in properties.properties:
            if prop.type == 'SpreadElement':
                self._scan_mapgetters(prop.argument)
            elif prop.type == 'Property':
                name = prop.key.name
                body = self._node_to_string(prop.value)
                # remove () => { return ... } from computed properties using regex
                body = re.sub(r'\(\) => \{ return (.*)\}', r'\1', body)
                self.component.computed[name] = body
            else:
                print(f"DEBUG: Unexpected property type in computed: {prop.type}")

        print(f"DEBUG: Final computed properties: {self.component.computed}")

    def _scan_mapgetters(self, node):
        if node.type == 'CallExpression' and node.callee.name == 'mapGetters':
            self.component.uses_vuex = True
            if node.arguments and hasattr(node.arguments[0], 'type') and node.arguments[0].type == 'ArrayExpression':
                for element in node.arguments[0].elements:
                    if hasattr(element, 'type') and element.type == 'Literal':
                        getter_name = element.value
                        self.component.computed[getter_name] = f"store.getters.{getter_name}"
                    else:
                        print(f"DEBUG: Unexpected element type in mapGetters: {getattr(element, 'type', 'Unknown')}")
            else:
                print("DEBUG: Unexpected argument structure in mapGetters call")

    def _node_to_string(self, node):
        if node.type in ['FunctionExpression', 'ArrowFunctionExpression']:
            params = ', '.join([p.name for p in node.params])
            body = self._node_to_string(node.body)
            # if only one parameterm, remove parentheses
            if len(node.params) == 1:
                return f"{params} => {body}"
            return f"({params}) => {body}"
        elif node.type == 'BlockStatement':
            statements = [self._node_to_string(stmt) for stmt in node.body]
            return '{ ' + '; '.join(statements) + ' }'
        elif node.type == 'ReturnStatement':
            return f"return {self._node_to_string(node.argument)}"
        elif node.type == 'IfStatement':
            condition = self._node_to_string(node.test)
            consequent = self._node_to_string(node.consequent)
            alternate = self._node_to_string(node.alternate) if node.alternate else None
            if alternate:
                return f"if ({condition}) {consequent} else {alternate}"
            else:
                return f"if ({condition}) {consequent}"
        elif node.type == 'ExpressionStatement':
            return self._node_to_string(node.expression)
        elif node.type == 'AssignmentExpression':
            left = self._node_to_string(node.left)
            right = self._node_to_string(node.right)
            return f"{left} = {right};"
        elif node.type == 'VariableDeclaration':
            declarations = [self._node_to_string(decl) for decl in node.declarations]
            return f"{node.kind} {', '.join(declarations)}"
        elif node.type == 'VariableDeclarator':
            id_str = self._node_to_string(node.id)
            init_str = self._node_to_string(node.init) if node.init else None
            return f"{id_str} = {init_str}" if init_str else id_str
        elif node.type == 'BinaryExpression':
            left = self._node_to_string(node.left)
            right = self._node_to_string(node.right)
            return f"{left} {node.operator} {right}"
        elif node.type == 'UnaryExpression':
            argument = self._node_to_string(node.argument)
            if node.operator == '!' and node.argument.type == 'LogicalExpression':
                return f"{node.operator}({argument})"
            return f"{node.operator}{argument}"
        elif node.type == 'LogicalExpression':
            left = self._node_to_string(node.left)
            right = self._node_to_string(node.right)
            if node.left.type == 'LogicalExpression' and node.left.operator != node.operator:
                left = f"({left})"
            if node.right.type == 'LogicalExpression' and node.right.operator != node.operator:
                right = f"({right})"
            return f"{left} {node.operator} {right}"
        elif node.type == 'Literal':
            if isinstance(node.value, bool):
                return str(node.value).lower()
            return repr(node.value)
        elif node.type == 'Identifier':
            return node.name
        elif node.type == 'MemberExpression':
            obj = self._node_to_string(node.object)
            if node.computed:
                prop = self._node_to_string(node.property)
                return f"{obj}[{prop}]"
            else:
                prop = self._node_to_string(node.property)
                return f"{obj}.{prop}"
        elif node.type == 'CallExpression':
            callee = self._node_to_string(node.callee)
            args = ', '.join([self._node_to_string(arg) for arg in node.arguments])
            return f"{callee}({args})"
        elif node.type == 'ThisExpression':
            return 'this'
        elif node.type == 'ArrayExpression':
            elements = [self._node_to_string(el) for el in node.elements]
            return f"[{', '.join(elements)}]"
        elif node.type == 'ObjectExpression':
            properties = [f"{p.key.name}: {self._node_to_string(p.value)}" for p in node.properties]
            return f"{{{', '.join(properties)}}}"
        else:
            return f"/* Unsupported node type: {node.type} */"

    def _scan_imports(self, parsed):
        for node in parsed.body:
            if node.type == 'ImportDeclaration':
                source = node.source.value
                default_specifiers = []
                named_specifiers = []
                for specifier in node.specifiers:
                    if specifier.type == 'ImportDefaultSpecifier':
                        default_specifiers.append(specifier.local.name)
                    elif specifier.type == 'ImportSpecifier':
                        named_specifiers.append(specifier.imported.name)

                if default_specifiers and named_specifiers:
                    import_str = f"import {', '.join(default_specifiers)}, {{ {', '.join(named_specifiers)} }} from '{source}'"
                elif default_specifiers:
                    import_str = f"import {', '.join(default_specifiers)} from '{source}'"
                elif named_specifiers:
                    import_str = f"import {{ {', '.join(named_specifiers)} }} from '{source}'"
                else:
                    continue

                self.component.imports.add(import_str)
        print(f"DEBUG: Scanned imports: {self.component.imports}")