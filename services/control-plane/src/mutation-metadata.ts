import { SetMetadata } from "@nestjs/common";

/** Trusted handler metadata: responses containing one-time secrets cannot be cached. */
export const SECRET_MUTATION_RESPONSE = Symbol("control.secret-mutation-response");
export const SecretMutationResponse = () => SetMetadata(SECRET_MUTATION_RESPONSE, true);
