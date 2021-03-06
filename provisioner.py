"""
Creates a SAML provider and associated trust role with no attached policies in the current account.
Also creates a json blob to paste in the AWS application manifest in AD
"""
import json
import logging

from provisioner.iam_helpers import saml, roles
from provisioner.cfn_helpers.stacks import create_stack, update_stack
from provisioner.cfn_helpers.templates import validate_template
from provisioner.exceptions import (SAMLProviderExistsError,
                                    NoUpdateToPerformError,
                                    StackExistsError,
                                    RoleNotFoundError)
from provisioner.ad_helpers import approles

def setup_logger():
    """
    Set up all the stuff to get the logger configured and working
    """
    logger = logging.getLogger('provisioner')
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    return logger

__logger__ = setup_logger()


def process_params(params_file, saml_provider_arn, role_name):
    """
    Process the parameters json file and returns a dict with the results.

    Will set a property key of `SAMLProviderARN` to whatever saml_provider_arn is passed in

    Will set a property key of `RoleName` to whatever role_name is passed in
    """
    params = json.load(open(params_file, 'r'))
    for param in params:
        if 'SAMLProviderARN' in param['ParameterKey']:
            param['ParameterValue'] = saml_provider_arn
        if 'RoleName' in param['ParameterKey']:
            param['ParameterValue'] = role_name
    __logger__.debug("Parameters:\n %s", params)
    return params

def main(args):
    "Let's make us some roles!"
    __logger__.info("Adding SAML provider to Account...")
    saml_provider_arn = None
    stack_name = args.stack_name
    role_name = args.role_name
    template_path = args.template_path
    params_file = args.params_file
    try:
        saml_provider_arn = saml.add_saml_provider(args.saml_metadata, args.provider_name)
    except SAMLProviderExistsError:
        __logger__.info("SAML provider %s already exists. Looking up ARN...", args.provider_name)
        saml_provider_arn = saml.look_up_saml_provider(args.provider_name)
    __logger__.debug("Identity Provider: %s", saml_provider_arn)

    __logger__.info("Adding Role to account...")
    try:
        parameters = process_params(params_file, saml_provider_arn, role_name)
        __logger__.debug("Validating template '%s'", template_path)
        validate_template(template_path)
        stack_id = create_stack(stack_name, template_path, parameters)
        __logger__.info("Stack created. ID: %s", stack_id)
    except StackExistsError:
        __logger__.info("Stack %s already exists. Updating stack instead.", stack_name)
        try:
            response = update_stack(stack_name, template_path, parameters)
            __logger__.debug("Stack updated successfully. Response: %s", response)
        except NoUpdateToPerformError:
            __logger__.debug("Stack does not require Updating.")

    __logger__.info("Looking up role ARN...")
    try:
        role_data = roles.look_up_role(role_name)
        trust_role_arn = role_data['Role']['Arn']
        __logger__.debug("Role Found: %s", trust_role_arn)
    except RoleNotFoundError:
        __logger__.warning("Couldn't find role %s", role_name)
        raise

    __logger__.info("Generating appRoles JSON blob...")
    approles_blob = approles.generate_ad_role(args.role_name,
                                              args.role_description,
                                              trust_role_arn,
                                              saml_provider_arn)
    __logger__.debug("appRoles json generated:")
    __logger__.info("\n%s", json.dumps(approles_blob, sort_keys=True, indent=4))


if __name__ == "__main__":
    import argparse
    __parser__ = argparse.ArgumentParser(description="Set up AWS account for SAML auth")
    __parser__.add_argument('-m --saml_metadata',
                            type=str,
                            required=True,
                            help='file containing AD cert metadata',
                            dest='saml_metadata')
    __parser__.add_argument('-t --cfn_template',
                            type=str,
                            required=True,
                            help='path to cloudformation template',
                            dest='template_path')
    __parser__.add_argument('-p --cfn_parameters',
                            type=str,
                            help='path to cloudformation parameters file',
                            dest='params_file')
    __parser__.add_argument('-s --stack_name',
                            type=str,
                            help='name of the cloudformation stack',
                            dest='stack_name',
                            default='federated-trust-role-and-policy')
    __parser__.add_argument('-i --idp_name',
                            type=str,
                            help='name to assign to the identity provider',
                            dest="provider_name",
                            default="new_saml_provider")
    __parser__.add_argument('-r --role_name',
                            type=str,
                            help="name to assign to the role created",
                            dest="role_name",
                            default="new_saml_role")
    __parser__.add_argument('-d --role_description',
                            type=str,
                            help="description to assign to the role created",
                            dest="role_description",
                            default="A role created by")
    __args__ = __parser__.parse_args()
    main(__args__)
