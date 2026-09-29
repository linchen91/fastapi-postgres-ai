# ONE-TIME MIGRATION (helm adoption): the stack moved from raw kubernetes_*
# resources to the helm_release in helm.tf. These `removed` blocks make
# Terraform forget the old objects (destroy = false) so they stay in the
# cluster and are adopted by helm_release.app (take_ownership = true) instead
# of being destroyed.
#
# DELETE THIS FILE after the first successful `terraform apply`.

removed {
  from = kubernetes_config_map.app

  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_secret.app

  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_deployment.api

  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_deployment.postgres

  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_service.api

  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_service.postgres

  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_persistent_volume_claim.postgres

  lifecycle {
    destroy = false
  }
}
