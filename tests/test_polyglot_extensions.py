import pytest
import os
import tempfile
from agent_engine.tools.ast_ops import get_entity_coordinates, get_references

@pytest.mark.asyncio
async def test_typescript_extensions():
    ts_content = """
    export interface UserProfile {
        username: string;
        email: string;
    }
    
    type PayoutRate = number;
    
    const calculateBonus = (base: number): number => {
        return base * 0.15;
    };
    """
    with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
        f.write(ts_content.encode("utf-8"))
        path = f.name
        
    try:
        # 1. Locate interface_declaration
        res_interface = await get_entity_coordinates(path, "UserProfile", entity_type="class")
        assert res_interface["found"] is True
        assert "interface UserProfile" in res_interface["original_text_guard"]
        
        # 2. Locate type_alias_declaration
        res_alias = await get_entity_coordinates(path, "PayoutRate", entity_type="class")
        assert res_alias["found"] is True
        assert "PayoutRate = number" in res_alias["original_text_guard"]
        
        # 3. Locate arrow_function / lexical_declaration
        res_func = await get_entity_coordinates(path, "calculateBonus", entity_type="function")
        assert res_func["found"] is True
        assert "calculateBonus" in res_func["original_text_guard"]
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_go_extensions():
    go_content = """
    package main
    
    import "fmt"
    
    type Config struct {
        BaseURL string
        Timeout int
    }
    
    func main() {
        fmt.Println("Hello Go")
    }
    """
    with tempfile.NamedTemporaryFile(suffix=".go", delete=False) as f:
        f.write(go_content.encode("utf-8"))
        path = f.name
        
    try:
        # 1. Locate type_spec / struct in Go
        res_struct = await get_entity_coordinates(path, "Config", entity_type="class")
        assert res_struct["found"] is True
        assert "Config struct" in res_struct["original_text_guard"]
        
        # 2. Match package_identifier references
        res_refs = await get_references(path, "main")
        assert res_refs["total_count"] >= 2  # 'package main' and 'func main()'
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_rust_extensions():
    rust_content = """
    struct Order {
        id: u64,
        amount: f64,
    }
    
    trait Summarizable {
        fn summarize(&self) -> String;
    }
    """
    with tempfile.NamedTemporaryFile(suffix=".rs", delete=False) as f:
        f.write(rust_content.encode("utf-8"))
        path = f.name
        
    try:
        # 1. Locate struct_item in Rust
        res_struct = await get_entity_coordinates(path, "Order", entity_type="class")
        assert res_struct["found"] is True
        assert "struct Order" in res_struct["original_text_guard"]
        
        # 2. Locate trait_item in Rust
        res_trait = await get_entity_coordinates(path, "Summarizable", entity_type="class")
        assert res_trait["found"] is True
        assert "trait Summarizable" in res_trait["original_text_guard"]
    finally:
        if os.path.exists(path):
            os.remove(path)
