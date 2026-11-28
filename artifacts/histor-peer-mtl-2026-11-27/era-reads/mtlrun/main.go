// mtlrun [-by-name] FILE... — the MCP Transparency Log's own JCSToolsDigest (pkg/canon, copied unchanged from
// the commit in SOURCE.txt) over saved tools/list results (a JSON array of tools).
// -by-name first gathers the tools the way its cmd/mcpobs toolsOf does: a map keyed by name, so a later tool
// with a name already seen replaces the earlier one and a tool with no name is left out.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"mtlrun/canon"
)

func main() {
	args := os.Args[1:]
	byName := len(args) > 0 && args[0] == "-by-name"
	if byName {
		args = args[1:]
	}
	for _, path := range args {
		raw, err := os.ReadFile(path)
		if err != nil {
			fmt.Println(path, err)
			continue
		}
		var tools []json.RawMessage
		if err := json.Unmarshal(raw, &tools); err != nil {
			fmt.Println(path, err)
			continue
		}
		listed := len(tools)
		if byName {
			m := map[string]json.RawMessage{}
			for _, t := range tools {
				var nm struct {
					Name string `json:"name"`
				}
				if json.Unmarshal(t, &nm) == nil && nm.Name != "" {
					m[nm.Name] = t
				}
			}
			tools = tools[:0]
			for _, t := range m {
				tools = append(tools, t)
			}
		}
		d, reason, err := canon.JCSToolsDigest(tools)
		fmt.Println(d, reason, err, "listed", listed, "digested", len(tools), path)
	}
}
