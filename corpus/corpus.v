(* Corpus de preuves pour la recherche d'exemples similaires (retrieval).

   Inspiré de Rango (Thompson et al., 2024) et RocqStar (Khramov et al., 2025),
   qui ajoutent au contexte du LLM des preuves proches de l'énoncé visé.

   Règle anti-fuite : aucun énoncé du benchmark n'apparaît ici. Les lemmes portent
   sur d'AUTRES structures (registres, listes d'options, compteurs) ; ils
   montrent des schémas de preuve (induction, destruct, lia, discriminate) que
   l'agent peut réutiliser, sans jamais lui donner la réponse.
   Vérifié par tests/test_benchmark.py (aucun nom ni énoncé partagé).
*)

From Coq Require Import List Arith Lia.
Import ListNotations.

(* Banc de registres : une fonction des indices vers les valeurs. *)
Definition regs := nat -> nat.

Definition update (r : regs) (k v : nat) : regs :=
  fun x => if Nat.eqb x k then v else r x.

Fixpoint replace (l : list nat) (n v : nat) : list nat :=
  match l, n with
  | [], _ => []
  | _ :: t, 0 => v :: t
  | x :: t, S k => x :: replace t k v
  end.

Fixpoint lookup (l : list nat) (n : nat) : option nat :=
  match l, n with
  | [], _ => None
  | x :: _, 0 => Some x
  | _ :: t, S k => lookup t k
  end.

Fixpoint sum (l : list nat) : nat :=
  match l with
  | [] => 0
  | x :: t => x + sum t
  end.

(* @theorem update_eq | facile *)
Lemma update_eq : forall (r : regs) (k v : nat), update r k v k = v.
Proof.
  intros r k v. unfold update. rewrite Nat.eqb_refl. reflexivity.
Qed.

(* @theorem update_neq | moyen *)
Lemma update_neq : forall (r : regs) (k x v : nat),
  x <> k -> update r k v x = r x.
Proof.
  intros r k x v H. unfold update.
  destruct (Nat.eqb x k) eqn:E.
  - apply Nat.eqb_eq in E. contradiction.
  - reflexivity.
Qed.

(* @theorem replace_length | facile *)
Lemma replace_length : forall (l : list nat) (n v : nat),
  length (replace l n v) = length l.
Proof.
  induction l as [| x t IH]; intros n v.
  - reflexivity.
  - destruct n as [| k]; simpl; [reflexivity | rewrite IH; reflexivity].
Qed.

(* @theorem lookup_beyond | moyen *)
Lemma lookup_beyond : forall (l : list nat) (n : nat),
  length l <= n -> lookup l n = None.
Proof.
  induction l as [| x t IH]; intros n H.
  - reflexivity.
  - destruct n as [| k]; simpl in *; [lia | apply IH; lia].
Qed.

(* @theorem lookup_replace_neq | moyen *)
Lemma lookup_replace_neq : forall (l : list nat) (n p v : nat),
  n <> p -> lookup (replace l n v) p = lookup l p.
Proof.
  induction l as [| x t IH]; intros n p v H.
  - reflexivity.
  - destruct n as [| k], p as [| q]; simpl.
    + contradiction.
    + reflexivity.
    + reflexivity.
    + apply IH. lia.
Qed.

(* @theorem lookup_some_lt | moyen *)
Lemma lookup_some_lt : forall (l : list nat) (n v : nat),
  lookup l n = Some v -> n < length l.
Proof.
  induction l as [| x t IH]; intros n v H.
  - discriminate H.
  - destruct n as [| k]; simpl in *.
    + lia.
    + apply IH in H. lia.
Qed.

(* @theorem sum_app | moyen *)
Lemma sum_app : forall l1 l2 : list nat, sum (l1 ++ l2) = sum l1 + sum l2.
Proof.
  induction l1 as [| x t IH]; intros l2; simpl.
  - reflexivity.
  - rewrite IH. lia.
Qed.

(* @theorem mul_one_right | facile *)
Lemma mul_one_right : forall n : nat, n * 1 = n.
Proof.
  induction n as [| k IH]; simpl; [reflexivity | rewrite IH; reflexivity].
Qed.

(* @theorem map_length_c | facile *)
Lemma map_length_c : forall (f : nat -> nat) (l : list nat),
  length (map f l) = length l.
Proof.
  intros f. induction l as [| x t IH]; simpl; [reflexivity | rewrite IH; reflexivity].
Qed.

(* @theorem ltb_false_le | moyen *)
Lemma ltb_false_le : forall n m : nat, (n <? m) = false -> m <= n.
Proof.
  intros n m H. apply Nat.ltb_ge in H. exact H.
Qed.
