#!/bin/bash
# Writes the scenes of an episode one after another, each on a headline the earlier ones did not use.
#   ./episode_write.sh ep1 "Officer Bolt,Captain Mira:beach" "Chef Basil,Dr. Ada:city" ...
set -e
EP=$1; shift
mkdir -p episodes/$EP
echo "[]" > episodes/$EP/used.json
i=1
for spec in "$@"; do
  cast=${spec%%:*}; setting=${spec##*:}
  ~/doodle-env312/bin/python scene_writer.py --seed $((100 + i)) --cast "$cast" --setting "$setting" \
      --exclude episodes/$EP/used.json --out episodes/$EP/scene$i.json 2>&1 | grep -v -i warn
  ~/doodle-env312/bin/python -c "import json; u=json.load(open('episodes/$EP/used.json')); u.append(json.load(open('episodes/$EP/scene$i.json'))['news']['title']); json.dump(u, open('episodes/$EP/used.json','w'))"
  i=$((i + 1))
done
