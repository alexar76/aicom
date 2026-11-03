import gzip, json, sys
want = set(open(sys.argv[1]).read().split())
with gzip.open(sys.argv[2], "rt") as f, gzip.open(sys.argv[3], "wt") as out:
    for line in f:
        d = line[11:line.index('"', 11)] if line.startswith('{"digest":"') else json.loads(line)["digest"]
        if d in want:
            out.write(line)
