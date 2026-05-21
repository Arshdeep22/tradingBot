#!/usr/bin/env python3
"""
Polls OCI for A1.Flex capacity across all availability domains and launches
the instance as soon as a slot opens. Run once; it exits on success or Ctrl+C.

Prerequisites:
  pip install oci
  oci setup config   (creates ~/.oci/config)

Fill in the CONFIG block below before running.
"""

import time
import sys
import oci
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
COMPARTMENT_ID  = "ocid1.compartment.oc1..REPLACE_ME"
SUBNET_ID       = "ocid1.subnet.oc1..REPLACE_ME"
IMAGE_ID        = "ocid1.image.oc1..REPLACE_ME"        # Ubuntu 22.04 ARM
SSH_PUBLIC_KEY  = "ssh-rsa REPLACE_ME your@email"      # contents of ~/.ssh/id_rsa.pub

DISPLAY_NAME    = "tradingbot"
SHAPE           = "VM.Standard.A1.Flex"
OCPUS           = 2
MEMORY_GB       = 12

RETRY_INTERVAL  = 120   # seconds between attempts
OCI_CONFIG_FILE = "~/.oci/config"
OCI_PROFILE     = "DEFAULT"
# ── END CONFIG ────────────────────────────────────────────────────────────────


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_availability_domains(identity_client: oci.identity.IdentityClient) -> list[str]:
    ads = identity_client.list_availability_domains(COMPARTMENT_ID).data
    return [ad.name for ad in ads]


def try_launch(compute_client: oci.core.ComputeClient, ad: str) -> oci.core.models.Instance | None:
    details = oci.core.models.LaunchInstanceDetails(
        compartment_id=COMPARTMENT_ID,
        availability_domain=ad,
        display_name=DISPLAY_NAME,
        shape=SHAPE,
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=OCPUS,
            memory_in_gbs=MEMORY_GB,
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            image_id=IMAGE_ID,
            source_type="image",
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=SUBNET_ID,
            assign_public_ip=True,
        ),
        metadata={
            "ssh_authorized_keys": SSH_PUBLIC_KEY,
            "user_data": "",
        },
    )
    try:
        response = compute_client.launch_instance(details)
        return response.data
    except oci.exceptions.ServiceError as e:
        if e.status == 500 and "Out of host capacity" in (e.message or ""):
            return None
        raise


def main() -> None:
    if "REPLACE_ME" in COMPARTMENT_ID:
        print("ERROR: Fill in the CONFIG block before running.")
        sys.exit(1)

    config = oci.config.from_file(OCI_CONFIG_FILE, OCI_PROFILE)
    identity = oci.identity.IdentityClient(config)
    compute  = oci.core.ComputeClient(config)

    ads = get_availability_domains(identity)
    log(f"Found {len(ads)} availability domain(s): {ads}")
    log(f"Polling every {RETRY_INTERVAL}s — press Ctrl+C to stop.")

    attempt = 0
    while True:
        attempt += 1
        for ad in ads:
            log(f"Attempt {attempt} — trying {ad} ...")
            instance = try_launch(compute, ad)
            if instance:
                log(f"SUCCESS — instance launched in {ad}")
                log(f"  OCID:  {instance.id}")
                log(f"  State: {instance.lifecycle_state}")
                log("Waiting ~60s for public IP to be assigned...")
                time.sleep(60)
                vnic_attachments = compute.list_vnic_attachments(
                    compartment_id=COMPARTMENT_ID,
                    instance_id=instance.id,
                ).data
                if vnic_attachments:
                    vnic_client = oci.core.VirtualNetworkClient(config)
                    vnic = vnic_client.get_vnic(vnic_attachments[0].vnic_id).data
                    log(f"  Public IP: {vnic.public_ip}")
                    log("")
                    log("Next steps:")
                    log(f"  ssh ubuntu@{vnic.public_ip}")
                    log("  git clone https://github.com/Arshdeep22/tradingBot")
                    log("  pip install -r tradingBot/requirements.txt")
                    log("  # add crontab entries — see MANUAL.md")
                sys.exit(0)
            else:
                log(f"  No capacity in {ad}.")

        log(f"All ADs full. Retrying in {RETRY_INTERVAL}s ...\n")
        time.sleep(RETRY_INTERVAL)


if __name__ == "__main__":
    main()
