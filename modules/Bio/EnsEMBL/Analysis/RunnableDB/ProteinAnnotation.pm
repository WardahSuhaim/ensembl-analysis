
=head1 NAME

ProteinAnnotation.pm - DESCRIPTION of Object

=head1 SYNOPSIS

this is the base class for the ProteinAnnotation runnabledbs

=head1 DESCRIPTION

=head1 CONTACT

ensembl-dev@ebi.ac.uk

=cut

package Bio::EnsEMBL::Analysis::RunnableDB::ProteinAnnotation;
use vars qw(@ISA);
use strict;
use Bio::EnsEMBL::Analysis::RunnableDB;
use Bio::EnsEMBL::DBSQL::ProteinFeatureAdaptor;
use Bio::EnsEMBL::Analysis::Config::ProteinAnnotation;

use Bio::EnsEMBL::Utils::Exception qw(throw warning);

@ISA = qw (Bio::EnsEMBL::Analysis::RunnableDB);


################################
sub new {
  my ($class, @args) = @_;
  my $self = $class->SUPER::new(@args);
  
  throw("Analysis object required") unless ($self->analysis);

  $self->read_and_check_config;
  
  return $self;
}


################################
sub fetch_input {
  my ($self) = @_;  
  my $input_id;
 
  if($self->INPUT_ID_TYPE eq 'FILE'){
    $input_id = $self->BASE_DIR . "/" . $self->input_id;
    throw($input_id." doesn't exist\n") unless(-e $input_id);
  } elsif($self->INPUT_ID_TYPE eq 'TRANSLATIONID'){
    my $prot;
    eval {
      $prot = $self->db->get_TranslationAdaptor->fetch_by_dbID($self->input_id);
    };
    if($@ or not defined $prot) {
      throw($self->input_id.
            " either isn't a transcript dbID ".
            " or doesn't exist in the database : $@\n");
    }
    
    $input_id  =  Bio::PrimarySeq->new(-seq         => $prot->seq,
				       -id          => $self->input_id,
				       -accession   => $self->input_id,
				       -moltype     => 'protein');
  } else {
    throw("Input id type '" . $self->INPUT_ID_TYPE . "' not recognised");
  }
  
  $self->query($input_id);
}


##################################
sub write_output {
  my($self) = @_;
  
  my @features = @{$self->output()};
    
  my $adap = $self->db->get_ProteinFeatureAdaptor;  
  
  foreach my $feat(@features) {
    $adap->store($feat, $feat->seqname);
  }
  
  return 1;
}



##################################
sub run {
  my ($self,$dir) = @_;
  throw("Runnable module not set") unless ($self->runnable());
  throw("Input not fetched") unless ($self->query());

  my @res;
  foreach my $r (@{$self->runnable}) {
    $r->run($dir);
    push @res, @{$r->output};
  }

  @res = @{$self->filter_results(\@res)};

  $self->output(\@res);
}


###################################
sub query{
  my ($self, $query) = @_;

  if(defined $query){
    if (ref($query)) {      
      if (not $query->isa('Bio::PrimarySeqI')) {
        throw("Must pass RunnableDB:query a Bio::PrimarySeqI " 
              . "not a ".$query);
      } 
    } elsif (not -e $query) {
      throw("Must pass RunnableDB::query a filename that exists " . ref($query));
    }
    $self->{_query} = $query;        
  }
  return $self->{_query};
}

#####################################
sub output {
  my ($self, $output) = @_;
  if(!$self->{'output'}){
    $self->{'output'} = [];
  }
  if($output){
    if(ref($output) ne 'ARRAY'){
      throw('Must pass RunnableDB:output an array ref not a '.$output);
    }
    $self->{'output'} = $output;
  }
  return $self->{'output'};
}

##################################
sub filter_results {
  my ($self, $list) = @_;

  # default implementation; no filtering
  return $list;
}

####################################
#############################################################
# Declare and set up config variables
#############################################################

sub read_and_check_config {
  my $self = shift;

  $self->SUPER::read_and_check_config($PROTEINANNOTATION_CONFIG_BY_LOGIC);

  ##########
  # CHECKS
  ##########
  my $logic = $self->analysis->logic_name;

  # check that compulsory options have values
  foreach my $config_var (qw(INPUT_ID_TYPE)) {
    throw("You must define $config_var in config for logic '$logic'")
        if not defined $self->$config_var;
  }

  if ($self->INPUT_ID_TYPE eq 'FILE' and 
      not defined $self->BASE_DIR) {
    throw("You must define BASE_DIR in config for logic '$logic' ". 
          "(input_id_type=FILE)")
  }

}


sub INPUT_ID_TYPE {
  my ($self, $val) = @_;

  if (defined $val) {
    $self->{_input_id_type} = $val;
  }

  return $self->{_input_id_type};
}


sub BASE_DIR {
  my ($self, $val) = @_;

  if (defined $val) {
    $self->{_base_dir} = $val;
  }

  return $self->{_base_dir};
}


1;
