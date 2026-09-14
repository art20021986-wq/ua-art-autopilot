# Observer v3 — exact metadata review

The metadata-only16:44 observation lists exactly17 regular hidden files, no hidden directories, and no directory changes during scanning. Its exact received bytes have SHA25624759ba72008742d32b1953ee971e450359f5d3d76761863f70164e14fcdb2fe; root independently confirmed the same server SHA256 through the authenticated hosting console. No file content was read to prepare this change.

The delivery wrapper now permits only those17 exact absolute paths, and only when each remains a regular non-symlink file at the exact resolved path, UID23671234 equal to the current process UID, GID60000, mode0664 and the individually observed byte size. It requires the complete observed hidden path set to match. Any unknown path, hidden directory, special file, symlink, metadata change or disappearance remains a visible block.

The startup-file exception remains byte-for-byte identical as a function. The original install observer626bb214… and engine3d74fc2a… remain unchanged. Their complete root-source/public-tree inventory still includes every allowed file and returns only hashes, sizes and modes; nothing is excluded, executed or emitted as source contents. The wrapper does not pin a Preview manifest or WSGI and therefore does not conflict with the new successful gallery Preview.

Validation covered all17 actual metadata records and rejection of wrong mode, owner, group, size, symlink, directory, unknown exact name and changed resolved path. No server or UI execution was performed. Earlier v1/v2 failures and kits remain preserved.

Frozen upload: /workspace/scratch/5f3dba772b24/server_transfer/install_obs_v3_1648.pyz,15,480bytes, SHA25648502613db498c1c347e62f5ea2d5dadedd1ff0ab6457bd6ebe2781c9560817c. Run python3.10 -I -B /home/Carix/autopilot_inbox/cloud/install_obs_v3_1648.pyz after confirming the metadata and kit server hashes. Embedded authenticated quota is the exact16:41:42.701Z observation, valid until17:11:42.701Z; after that supply a genuinely fresh quota file with --quota-json. Preserve exact stdout and server SHA256. The observer's PASS is input-observation scope only; full_preview stays NOT_PASSED and no production Gate is created.
