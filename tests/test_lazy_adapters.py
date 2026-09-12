import sys
import pytest

sys.path.insert(0, ".")

from yunta.adapters import (
    LanguageAdapterRegistry,
    PythonAdapter,
    JavaScriptTSAdapter,
    GoAdapter,
    RustAdapter,
    JSONAdapter,
    UniversalAdapter,
)
from yunta.tools.files import _validate_content
from yunta.tools.symbols import find_symbol, get_ast_outline


def test_lazy_loading_adapters():
    registry = LanguageAdapterRegistry()
    assert len(registry.loaded_adapter_names()) == 0

    adapter_ts = registry.get_adapter("src/index.ts")
    assert isinstance(adapter_ts, JavaScriptTSAdapter)
    assert registry.loaded_adapter_names() == ["JavaScriptTSAdapter"]

    adapter_go = registry.get_adapter("main.go")
    assert isinstance(adapter_go, GoAdapter)
    assert set(registry.loaded_adapter_names()) == {"JavaScriptTSAdapter", "GoAdapter"}


def test_python_adapter_validation():
    adapter = PythonAdapter()
    adapter.validate("def ok():\n    return 42\n")

    with pytest.raises(ValueError, match="sintaxis Python inválida"):
        adapter.validate("def bad_syntax(:")


def test_json_adapter_validation():
    adapter = JSONAdapter()
    adapter.validate('{"name": "yunta", "version": "2.2.0"}')

    with pytest.raises(ValueError, match="JSON inválido"):
        adapter.validate('{"name": "yunta",}')


def test_universal_adapter_bracket_balance():
    adapter = UniversalAdapter()
    adapter.validate("const x = { a: (1 + 2) };")

    with pytest.raises(ValueError, match="contenido desbalanceado"):
        adapter.validate("function test() { return (1 + 2;")


def test_ts_adapter_find_symbols_and_outline():
    adapter = JavaScriptTSAdapter()
    content = """
export interface User {
    id: string;
}

export class UserService {
    async getUser(id: string) {
        return null;
    }
}

export const fetchConfig = async () => {
    return {};
};
"""
    symbols = adapter.find_symbols(content, "User")
    names = [s["name"] for s in symbols]
    assert "User" in names
    assert "UserService" in names
    assert "getUser" in names

    outline = adapter.get_outline(content)
    assert any("interface User" in line for line in outline)
    assert any("class UserService" in line for line in outline)


def test_go_adapter_find_symbols():
    adapter = GoAdapter()
    content = """
package main

type Config struct {
    Port int
}

func NewConfig() *Config {
    return &Config{Port: 8080}
}
"""
    symbols = adapter.find_symbols(content)
    names = [s["name"] for s in symbols]
    assert "Config" in names
    assert "NewConfig" in names


def test_rust_adapter_find_symbols():
    adapter = RustAdapter()
    content = """
pub struct Client {
    url: String,
}

pub fn connect(url: &str) -> Client {
    Client { url: url.to_string() }
}
"""
    symbols = adapter.find_symbols(content)
    names = [s["name"] for s in symbols]
    assert "Client" in names
    assert "connect" in names


def test_java_adapter_find_symbols():
    from yunta.adapters import JavaAdapter
    adapter = JavaAdapter()
    content = """
package com.demo;

public class UserService {
    public String fetchUser(long id) {
        return "user";
    }
}
"""
    symbols = adapter.find_symbols(content)
    names = [s["name"] for s in symbols]
    assert "UserService" in names
    assert "fetchUser" in names


def test_csharp_adapter_find_symbols():
    from yunta.adapters import CSharpAdapter
    adapter = CSharpAdapter()
    content = """
namespace Demo {
    public class OrderService {
        public async Task<bool> ProcessOrderAsync(int id) {
            return true;
        }
    }
}
"""
    symbols = adapter.find_symbols(content)
    names = [s["name"] for s in symbols]
    assert "OrderService" in names
    assert "ProcessOrderAsync" in names


def test_additional_polyglot_adapters():
    from yunta.adapters import PHPAdapter, RubyAdapter, SwiftAdapter, ShellAdapter, SQLAdapter

    # PHP
    php = PHPAdapter()
    symbols_php = [s["name"] for s in php.find_symbols("<?php class ApiController { public function index() {} }")]
    assert "ApiController" in symbols_php
    assert "index" in symbols_php

    # Ruby
    rb = RubyAdapter()
    symbols_rb = [s["name"] for s in rb.find_symbols("class UserReport\n  def generate\n  end\nend")]
    assert "UserReport" in symbols_rb
    assert "generate" in symbols_rb

    # Swift
    swift = SwiftAdapter()
    symbols_swift = [s["name"] for s in swift.find_symbols("public struct Product {\n  public func buy() {}\n}")]
    assert "Product" in symbols_swift
    assert "buy" in symbols_swift

    # Shell
    sh = ShellAdapter()
    symbols_sh = [s["name"] for s in sh.find_symbols("deploy_app() {\n  echo ok\n}")]
    assert "deploy_app" in symbols_sh

    # SQL
    sql = SQLAdapter()
    symbols_sql = [s["name"] for s in sql.find_symbols("CREATE TABLE users (id INT PRIMARY KEY);")]
    assert "users" in symbols_sql


def test_files_validate_content_delegates_to_lazy_adapters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # Válidos
    _validate_content("main.py", "x = 10\n")
    _validate_content("config.json", '{"a": 1}')
    _validate_content("index.ts", "const a = 1;")
    _validate_content("Service.java", "public class Service {}")
    _validate_content("Order.cs", "public class Order {}")
    _validate_content("index.php", "<?php function test() {} ?>")
    _validate_content("app.rb", "def hello; end")
    _validate_content("script.sh", "function run() { echo hi; }")
    _validate_content("schema.sql", "CREATE TABLE t (id INT);")

    # Inválidos
    with pytest.raises(ValueError):
        _validate_content("bad.py", "def (")

    with pytest.raises(ValueError):
        _validate_content("bad.json", "{bad}")


