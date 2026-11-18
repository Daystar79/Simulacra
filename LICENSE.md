# Licensing for Simulacra

Simulacra is a hybrid project containing both software utilities and creative, conceptual specifications. To accommodate both, the project is licensed under a dual hybrid structure, with an explicit carve-out for author-local testing materials.

1. **Software & Scripts:** All executable code, utility scripts, and program files (including `.py` files such as `Framework/linter.py`, `deploy_framework.py`, `migrate_optimized.py`, and `scripts/**`) are licensed under the **MIT License**.
2. **Creative Content & Specifications:** All markdown manuals, guides, rules, the public character **template**, prompts, YAML configurations under `Framework/`, and the Roleplay **Simulator** runtime are licensed under the **Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0)**.
3. **Author-Local Materials (Not Licensed):** Named character cards and relationship maps are **not** part of the open-source grant. See [§3](#3-author-local-materials-all-rights-reserved).

---

## 1. MIT License (Software & Scripts)

Copyright (c) 2026 Cian Didymos

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 2. Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)

Copyright (c) 2026 Cian Didymos

This license applies to open specifications and scaffolding, including:

* `Framework/` manuals, rules, prompts, mechanics, YAML schemas, and empty ledger scaffolds (`Continuity_Ledger.md`, `Character_Change_Log.md`)
* `Simulator/` Roleplay / CharacterRuntime engine (interactive pre-draft character testing)
* `Characters/_template.yaml`, `Characters/_log_template.yaml`, and `Characters/README.md` (format documentation / scaffolds only)
* Project `README.md` and other top-level documentation not listed in §3

It does **not** apply to materials listed in §3.

### You are free to:
* **Share** — copy and redistribute the material in any medium or format.
* **Adapt** — remix, transform, and build upon the material for any purpose, even commercially.

### Under the following terms:
* **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made. You may do so in any reasonable manner, but not in any way that suggests the licensor endorses you or your use.
* **ShareAlike** — If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.
* **No additional restrictions** — You may not apply legal terms or technological measures that legally restrict others from doing anything the license permits.

For the full legal code of the CC BY-SA 4.0, please visit [creativecommons.org](https://creativecommons.org/licenses/by-sa/4.0/legalcode).

---

## 3. Author-Local Materials (All Rights Reserved)

Copyright (c) 2026 Cian Didymos. All rights reserved.

The following paths (and any substantially similar copies or renames) are included in this repository **for the author’s local testing and private use only**. They are **not** licensed under MIT or CC BY-SA 4.0. No permission is granted to use, copy, modify, merge, publish, distribute, sublicense, or create derivative works from these materials, except as required for personal inspection of this repository or as expressly authorized in writing by the copyright holder.

### Excluded paths

* **Named character cards** under `Characters/` other than `_template.yaml`, `_log_template.yaml`, and `README.md` (for example: cards for Cass, Helen, Lior, Nora, Reed, and Wren, and any future cast cards)
* **Named character logs** matching those cast members (`Characters/[slug]_log.yaml` when filled for author-local cast)
* **`Characters/Relations.md`** (cast relationship map)
* Historical backups or renames of the above under `backups_*` (named cards and relations only; framework/engine backups that are not cast content follow their open counterparts)

### Intent

* Downstream book projects and redistributions should use **`Characters/_template.yaml`** to build their own cast, then optionally drop in **`Simulator/CharacterRuntime.md`** (Character Pack load/save) to rehearse behaviour before drafting.
* `deploy_framework.py` does **not** distribute named cards or `Relations.md`; it **does** distribute `Simulator/`.
* User-created **Character Packs** (private card + memory files in cloud or local storage) are not part of this repository’s open-source grant unless the user publishes them.
* Presence of reserved files in the repo does **not** constitute an open-source license grant for those files.
