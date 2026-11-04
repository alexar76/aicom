// tilescheck PREFIX VKEY [OLD_SIZE] — follow a log through c2sp.org/tlog-tiles with the Go checksum database's
// tlog package (golang.org/x/mod/sumdb/tlog), which HISTOR's code shares nothing with: verify the checkpoint's
// log signature (golang.org/x/mod/sumdb/note), rebuild the root from the tiles (every tile checked against the
// signed root), prove consistency from OLD_SIZE, and check a few leaves against the entry bundles.
package main

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"

	"golang.org/x/mod/sumdb/note"
	"golang.org/x/mod/sumdb/tlog"
)

var prefix string

func get(path string) []byte {
	resp, err := http.Get(prefix + path)
	if err != nil {
		panic(err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		panic(fmt.Sprintf("GET %s: %d %s", path, resp.StatusCode, body))
	}
	return body
}

type reader struct{ fetched int }

func (r *reader) Height() int { return 8 }
func (r *reader) ReadTiles(tiles []tlog.Tile) ([][]byte, error) {
	out := make([][]byte, len(tiles))
	for i, t := range tiles {
		// sumdb paths are tile/8/L/N[.p/W]; c2sp.org/tlog-tiles drops the fixed height: tile/L/N[.p/W].
		out[i] = get(strings.Replace(t.Path(), "tile/8/", "tile/", 1))
		r.fetched++
	}
	return out, nil
}
func (r *reader) SaveTiles([]tlog.Tile, [][]byte) {}

func main() {
	prefix = strings.TrimRight(os.Args[1], "/") + "/"
	verifier, err := note.NewVerifier(os.Args[2])
	if err != nil {
		panic(err)
	}
	raw := get("checkpoint")
	n, err := note.Open(raw, note.VerifierList(verifier))
	if err != nil {
		panic(fmt.Sprintf("checkpoint signature: %v", err))
	}
	lines := strings.Split(n.Text, "\n")
	size, _ := strconv.ParseInt(lines[1], 10, 64)
	rootBytes, _ := base64.StdEncoding.DecodeString(lines[2])
	var root tlog.Hash
	copy(root[:], rootBytes)
	fmt.Printf("checkpoint %s size %d, log signature verified by %s\n", lines[0], size, n.Sigs[0].Name)

	tree := tlog.Tree{N: size, Hash: root}
	r := &reader{}
	hr := tlog.TileHashReader(tree, r)
	got, err := tlog.TreeHash(size, hr)
	if err != nil || got != root {
		panic(fmt.Sprintf("root from tiles: %v %v", got, err))
	}
	fmt.Printf("root rebuilt from %d tiles equals the signed root\n", r.fetched)

	if len(os.Args) > 3 {
		old, _ := strconv.ParseInt(os.Args[3], 10, 64)
		oldHash, err := tlog.TreeHash(old, hr)
		if err != nil {
			panic(err)
		}
		proof, err := tlog.ProveTree(size, old, hr)
		if err != nil {
			panic(err)
		}
		if err := tlog.CheckTree(proof, size, root, old, oldHash); err != nil {
			panic(fmt.Sprintf("consistency %d -> %d: %v", old, size, err))
		}
		fmt.Printf("consistency proof %d -> %d verified (%d hashes)\n", old, size, len(proof))
	}

	// Leaves: the first entry bundle (full or partial) against the tree.
	w := size
	if w > 256 {
		w = 256
	}
	bundlePath := "tile/entries/000"
	if w < 256 {
		bundlePath += ".p/" + strconv.FormatInt(w, 10)
	}
	bundle := get(bundlePath)
	checked := int64(0)
	for i := int64(0); i < w && len(bundle) >= 2; i++ {
		l := int(bundle[0])<<8 | int(bundle[1])
		entry := bundle[2 : 2+l]
		bundle = bundle[2+l:]
		if i%37 != 0 {
			continue
		}
		proof, err := tlog.ProveRecord(size, i, hr)
		if err != nil {
			panic(err)
		}
		if err := tlog.CheckRecord(proof, size, root, i, tlog.RecordHash(entry)); err != nil {
			panic(fmt.Sprintf("leaf %d: %v", i, err))
		}
		checked++
	}
	if !bytes.Equal(bundle, nil) && len(bundle) != 0 {
		panic("trailing bytes in the entry bundle")
	}
	fmt.Printf("%d entries of the first bundle proven included in the signed tree\n", checked)
}
