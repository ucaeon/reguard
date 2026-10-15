import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = json.loads((ROOT / 'infra/aws/single-node.json').read_text())


class AwsEvaluationTemplateTest(unittest.TestCase):
    def test_only_web_ports_are_public(self):
        rules = TEMPLATE['Resources']['WebSecurityGroup']['Properties']['SecurityGroupIngress']
        self.assertEqual({(r['FromPort'], r['ToPort'], r['IpProtocol']) for r in rules},
                         {(80, 80, 'tcp'), (443, 443, 'tcp')})
        types = {r['Type'] for r in TEMPLATE['Resources'].values()}
        self.assertFalse(types & {'AWS::EC2::EIP', 'AWS::EC2::NatGateway',
                                  'AWS::EKS::Cluster', 'AWS::RDS::DBInstance'})

    def test_billing_and_metadata_defaults(self):
        node = TEMPLATE['Resources']['Node']['Properties']
        self.assertEqual(node['CreditSpecification']['CPUCredits'], 'standard')
        self.assertEqual(node['MetadataOptions']['HttpTokens'], 'required')
        self.assertEqual(node['MetadataOptions']['HttpPutResponseHopLimit'], 1)
        self.assertEqual(node['InstanceInitiatedShutdownBehavior'], 'stop')
        disks = node['BlockDeviceMappings']
        self.assertEqual(sum(d['Ebs']['VolumeSize'] for d in disks), 60)
        self.assertTrue(all(d['Ebs']['Encrypted'] for d in disks))
        self.assertLessEqual(TEMPLATE['Parameters']['StopAfterHours']['MaxValue'], 144)

    def test_bootstrap_has_persistent_deadline_and_valid_shell(self):
        script = TEMPLATE['Resources']['Node']['Properties']['UserData']['Fn::Base64']['Fn::Sub']
        script = script.replace('${StopAfterHours}', '144')
        subprocess.run(['bash', '-n'], input=script, text=True, check=True)
        self.assertIn('Persistent=true', script)
        self.assertIn('if [ ! -s /var/lib/reguard/stop-at ]; then', script)
        self.assertIn('systemctl enable --now reguard-budget-stop.timer', script)

    def test_backups_are_private_retained_and_role_cannot_delete(self):
        backup = TEMPLATE['Resources']['Backups']
        self.assertEqual(backup['DeletionPolicy'], 'Retain')
        self.assertTrue(all(backup['Properties']['PublicAccessBlockConfiguration'].values()))
        statements = TEMPLATE['Resources']['NodeRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        actions = {a for s in statements for a in s['Action']}
        self.assertFalse(actions & {'s3:*', 's3:DeleteObject', 's3:DeleteBucket'})
        self.assertTrue({'s3:PutObject', 's3:GetObject'} <= actions)
        policy = TEMPLATE['Resources']['BackupPolicy']['Properties']['PolicyDocument']['Statement'][0]
        self.assertEqual(policy['Effect'], 'Deny')
        self.assertEqual(policy['Condition']['Bool']['aws:SecureTransport'], 'false')


if __name__ == '__main__':
    unittest.main()
