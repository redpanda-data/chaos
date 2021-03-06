[redpanda]
%{ for i, ip in redpanda_public_ips ~}
${ ip } ansible_user=${ ssh_user } ansible_become=True private_ip=${redpanda_private_ips[i]} id=${i}
%{ endfor ~}

[client]
%{ for i, ip in client_public_ips ~}
${ ip } ansible_user=${ ssh_user } ansible_become=True private_ip=${client_private_ips[i]} id=${i}
%{ endfor ~}

[control]
%{ for i, ip in control_public_ips ~}
${ ip } ansible_user=${ ssh_user } ansible_become=True private_ip=${control_private_ips[i]} id=${i}
%{ endfor ~}