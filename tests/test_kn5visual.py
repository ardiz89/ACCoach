"""Il modello grafico di una pista, letto in array.

Tutti i kn5 sono sintetici: i file veri del gioco non entrano nei test.
"""
from __future__ import annotations

import struct

import numpy as np
import pytest

from accoach import kn5visual as kv

_IDENT = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def _s(t):
    b = t.encode("utf-8")
    return struct.pack("<i", len(b)) + b


def _translate(x, y, z):
    """Matrice di un nodo di tipo 1, vettore riga: la traslazione sta in fondo."""
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


def mesh(name, verts, mat=0, uvs=None, nv=None):
    return ("mesh", name, verts, mat, uvs, nv)


def dummy(name, children, matrix=_IDENT):
    return ("dummy", name, children, matrix)


def skinned(name, verts):
    return ("skin", name, verts)


def _node(n):
    out = bytearray()
    if n[0] == "dummy":
        _, name, children, matrix = n
        out += struct.pack("<i", 1) + _s(name) + struct.pack("<i", len(children)) + b"\x01"
        out += struct.pack("<16f", *matrix)
        for c in children:
            out += _node(c)
        return out
    if n[0] == "skin":
        _, name, verts = n
        out += struct.pack("<i", 3) + _s(name) + struct.pack("<i", 0) + b"\x01"
        out += b"\x01\x01\x00"
        out += struct.pack("<i", 1) + _s("bone") + struct.pack("<16f", *_IDENT)
        out += struct.pack("<i", len(verts))
        for (x, y, z) in verts:
            # 44 byte come un vertice normale, piu' pesi e indici delle ossa
            out += struct.pack("<3f", x, y, z) + b"\x00" * (76 - 12)
        out += struct.pack("<i", len(verts))
        out += struct.pack(f"<{len(verts)}H", *range(len(verts)))
        out += struct.pack("<i", 0) + b"\x00" * 12
        return out
    _, name, verts, mat, uvs, nv = n
    out += struct.pack("<i", 2) + _s(name) + struct.pack("<i", 0) + b"\x01"
    out += b"\x01\x01\x00"
    out += struct.pack("<i", len(verts) if nv is None else nv)
    for k, (x, y, z) in enumerate(verts):
        u, v = uvs[k] if uvs else (0.0, 0.0)
        out += struct.pack("<3f", x, y, z) + struct.pack("<3f", 0, 1, 0)
        out += struct.pack("<2f", u, v) + struct.pack("<3f", 1, 0, 0)
    out += struct.pack("<i", len(verts))
    out += struct.pack(f"<{len(verts)}H", *range(len(verts)))
    out += struct.pack("<i", mat)
    out += b"\x00" * 12
    out += b"\x00" * 16 + b"\x01"
    return out


def _kn5(tmp_path, root, textures=(), materials=(), name="art.kn5", version=6):
    """Un kn5 con texture, materiali e un albero di nodi.

    ``textures`` e' [(nome, byte)], ``materials`` e'
    [(nome, shader, blend, alpha_test, [(slot, texture)])].
    """
    out = bytearray(b"sc6969" + struct.pack("<i", version))
    if version > 5:
        out += struct.pack("<i", 0)
    out += struct.pack("<i", len(textures))
    for tn, data in textures:
        out += struct.pack("<i", 1) + _s(tn) + struct.pack("<i", len(data)) + data
    out += struct.pack("<i", len(materials))
    for mn, shader, blend, at, maps in materials:
        out += _s(mn) + _s(shader) + bytes([blend, at])
        if version > 4:
            out += struct.pack("<i", 0)
        out += struct.pack("<i", 1) + _s("ksDiffuse") + struct.pack("<f", 0.4) + b"\x00" * 36
        out += struct.pack("<i", len(maps))
        for slot, tn in maps:
            out += _s(slot) + struct.pack("<i", 0) + _s(tn)
    out += _node(root)
    p = tmp_path / name
    p.write_bytes(bytes(out))
    return p


def _flat(x0, z0, x1, z1, y=0.0):
    """Due triangoli orizzontali che coprono un rettangolo."""
    a, b = (x0, y, z0), (x1, y, z0)
    c, d = (x1, y, z1), (x0, y, z1)
    return [a, b, c, a, c, d]


# --- matrici -----------------------------------------------------------------

def test_a_node_matrix_moves_its_children(tmp_path):
    p = _kn5(tmp_path, dummy("root", [
        dummy("moved", [mesh("a", _flat(0, 0, 1, 1))], _translate(10, 0, 5)),
    ]))
    m = kv.read(p)
    assert m.tris.dtype == np.float32 and m.tris.shape == (2, 3, 3)
    np.testing.assert_allclose(m.tris[0], [(10, 0, 5), (11, 0, 5), (11, 0, 6)], atol=1e-5)


def test_nested_nodes_compose_child_first_then_parent(tmp_path):
    """Vettore riga: prima la matrice del figlio, poi quella del padre. Con una
    rotazione nel padre e una traslazione nel figlio, l'ordine si vede."""
    # padre: yaw di 90 gradi, (1,0,0) -> (0,0,-1)
    yaw90 = (0, 0, -1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1)
    p = _kn5(tmp_path, dummy("root", [
        dummy("parent", [
            dummy("child", [mesh("a", [(0, 0, 0), (1, 0, 0), (0, 0, 1)])],
                  _translate(10, 0, 0)),
        ], yaw90),
    ]))
    m = kv.read(p)
    # figlio prima: (0,0,0)+(10,0,0) = (10,0,0), poi il padre la ruota in (0,0,-10)
    np.testing.assert_allclose(m.tris[0][0], (0, 0, -10), atol=1e-5)
    np.testing.assert_allclose(m.tris[0][1], (0, 0, -11), atol=1e-5)


def test_models_ini_position_and_rotation_are_applied(tmp_path):
    p = _kn5(tmp_path, dummy("root", [mesh("a", [(1, 0, 0), (2, 0, 0), (1, 0, 1)])]))
    turned = kv.read(p, rotation_deg=(90, 0, 0))
    np.testing.assert_allclose(turned.tris[0][0], (0, 0, -1), atol=1e-5)
    moved = kv.read(p, position=(100, 2, -50))
    np.testing.assert_allclose(moved.tris[0][0], (101, 2, -50), atol=1e-5)
    both = kv.read(p, position=(100, 0, 0), rotation_deg=(90, 0, 0))
    # prima la rotazione, poi la posizione
    np.testing.assert_allclose(both.tris[0][0], (100, 0, -1), atol=1e-5)


# --- materiali e texture -------------------------------------------------------

def test_the_diffuse_texture_is_found_by_its_slot(tmp_path):
    p = _kn5(tmp_path, dummy("root", [
        mesh("road", _flat(0, 0, 1, 1), mat=1,
             uvs=[(0, 0), (1, 0), (1, 1), (0, 0), (1, 1), (0, 1)]),
    ]), textures=[("mask.dds", b"MASKBYTES"), ("asphalt.dds", b"DIFFUSEBYTES!")],
        materials=[
            ("plain", "ksPerPixel", 0, 0, []),
            ("asph", "ksMultilayer", 1, 1, [("txMask", "mask.dds"),
                                             ("txDiffuse", "asphalt.dds")]),
        ])
    m = kv.read(p)
    assert [mt.name for mt in m.materials] == ["plain", "asph"]
    asph = m.materials[1]
    assert asph == kv.Material("asph", "ksMultilayer", 1, True, "asphalt.dds")
    assert m.materials[0].diffuse is None
    assert kv.texture_bytes(m, "asphalt.dds") == b"DIFFUSEBYTES!"
    assert kv.texture_bytes(m, "mask.dds") == b"MASKBYTES"
    assert kv.texture_bytes(m, "missing.dds") is None
    assert m.mat.tolist() == [1, 1]
    assert m.uv.dtype == np.float32
    np.testing.assert_allclose(m.uv[0], [(0, 0), (1, 0), (1, 1)])
    assert m.mesh_names == ["road"] and m.mesh.tolist() == [0, 0]


def test_a_collision_model_without_textures_or_materials_reads(tmp_path):
    """Il modello fisico (Monza `2.kn5`) non ha texture e forse nemmeno
    materiali: si legge lo stesso, e il materiale che non c'e' vale -1."""
    p = _kn5(tmp_path, dummy("root", [mesh("1ROAD_a", _flat(0, 0, 4, 4))]))
    m = kv.read(p)
    assert m.textures == {} and m.materials == []
    assert len(m.tris) == 2 and m.mat.tolist() == [-1, -1]


# --- cosa resta fuori ---------------------------------------------------------

def test_vertical_triangles_are_dropped(tmp_path):
    wall = [(0, 0, 0), (5, 0, 0), (5, 3, 0)]
    p = _kn5(tmp_path, dummy("root", [
        mesh("wall", wall), mesh("ground", _flat(0, 0, 1, 1)),
    ]))
    m = kv.read(p)
    assert len(m.tris) == 2
    assert m.mesh_names == ["ground"] and m.mesh.tolist() == [0, 0]


def test_skinned_meshes_are_skipped(tmp_path):
    p = _kn5(tmp_path, dummy("root", [
        skinned("flag", _flat(0, 0, 1, 1)), mesh("ground", _flat(5, 5, 6, 6)),
    ]))
    m = kv.read(p)
    assert m.mesh_names == ["ground"]
    assert float(m.tris[:, :, 0].min()) == pytest.approx(5.0)


def test_an_empty_model_gives_empty_arrays(tmp_path):
    p = _kn5(tmp_path, dummy("root", []))
    m = kv.read(p)
    assert m.tris.shape == (0, 3, 3) and m.uv.shape == (0, 3, 2)
    assert m.mat.shape == (0,) and m.mesh.shape == (0,)


# --- file che mentono ----------------------------------------------------------

def test_a_lying_count_is_refused(tmp_path):
    """Due miliardi di vertici in un file di poche centinaia di byte: lo dice
    il controllo dei conteggi, prima di leggere, non un MemoryError dopo."""
    p = _kn5(tmp_path, dummy("root", [mesh("a", _flat(0, 0, 1, 1), nv=2_000_000_000)]))
    with pytest.raises(ValueError, match="non stanno nel file"):
        kv.read(p)


def test_a_broken_file_is_a_value_error(tmp_path):
    p = tmp_path / "x.kn5"
    p.write_bytes(b"not a kn5 at all")
    with pytest.raises(ValueError):
        kv.read(p)
    good = _kn5(tmp_path, dummy("root", [mesh("a", _flat(0, 0, 1, 1))]), name="t.kn5")
    good.write_bytes(good.read_bytes()[:-30])
    with pytest.raises(ValueError):
        kv.read(good)
    with pytest.raises(OSError):
        kv.read(tmp_path / "missing.kn5")


def test_an_index_past_the_vertices_is_refused(tmp_path):
    p = _kn5(tmp_path, dummy("root", [mesh("a", _flat(0, 0, 1, 1))]))
    data = bytearray(p.read_bytes())
    # gli indici stanno subito dopo i 6 vertici: l'ultimo diventa 99
    at = data.rindex(struct.pack("<6H", 0, 1, 2, 3, 4, 5)) + 10
    data[at:at + 2] = struct.pack("<H", 99)
    p.write_bytes(bytes(data))
    with pytest.raises(ValueError):
        kv.read(p)
